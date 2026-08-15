from flask import Flask, render_template_string, request, jsonify
import re
import os
import sys
import subprocess
import difflib

app = Flask(__name__)

# Resolution order for the project folder to scan:
# 1) command-line argument:  python RUN.py "C:\path\to\project"
# 2) environment variable:   RPY_PROJECT_DIR
# 3) fallback: the folder this script lives in
if len(sys.argv) > 1:
    PROJECT_DIR = os.path.abspath(sys.argv[1])
elif os.environ.get('RPY_PROJECT_DIR'):
    PROJECT_DIR = os.path.abspath(os.environ['RPY_PROJECT_DIR'])
else:
    PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

TEXT_PATTERN = re.compile(r'^(\s*)(?:([a-zA-Z_]\w*)\s+)?"([^"\\]*(?:\\.[^"\\]*)*)"(\s*)$')
WORD_TOKEN_PATTERN = re.compile(r'\w+|[^\w\s]|\s+', re.UNICODE)


def tokenize_words(text):
    return WORD_TOKEN_PATTERN.findall(text)


def word_diff_segments(old_text, new_text):
    old_tokens = tokenize_words(old_text)
    new_tokens = tokenize_words(new_text)
    matcher = difflib.SequenceMatcher(None, old_tokens, new_tokens, autojunk=False)

    segments = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            segments.append({'op': 'equal', 'text': ''.join(old_tokens[i1:i2])})
        elif tag == 'delete':
            segments.append({'op': 'delete', 'text': ''.join(old_tokens[i1:i2])})
        elif tag == 'insert':
            segments.append({'op': 'insert', 'text': ''.join(new_tokens[j1:j2])})
        elif tag == 'replace':
            segments.append({'op': 'delete', 'text': ''.join(old_tokens[i1:i2])})
            segments.append({'op': 'insert', 'text': ''.join(new_tokens[j1:j2])})
    return segments

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
    <title>Редактор сценариев Ren'Py</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #181818; color: #d4d4d4; padding: 20px; margin: 0; }
        .container { width: 100%; max-width: none; padding: 0 20px; box-sizing: border-box; margin: 0; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; background: #222; padding: 15px 20px; border-radius: 8px; border: 1px solid #333; gap: 15px; }
        .controls { display: flex; align-items: center; gap: 10px; flex-grow: 1; min-width: 0; }
        .controls label { white-space: nowrap; flex-shrink: 0; }
        select { background: #2a2a2a; color: #fff; border: 1px solid #444; padding: 8px 12px; border-radius: 6px; font-size: 14px; flex-grow: 1; max-width: 250px; cursor: pointer; }
        select:focus { border-color: #007acc; outline: none; }

        button { background: #0e639c; color: white; border: none; padding: 9px 20px; cursor: pointer; border-radius: 6px; font-weight: bold; font-size: 14px; transition: all 0.2s; white-space: nowrap; }
        button:hover { background: #1177bb; }
        button:disabled { background: #444; color: #888; cursor: not-allowed; }

        .btn-reload { background: #333; }
        .btn-reload:hover { background: #444; }

        .info { color: #888; font-size: 13px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }

        .counter-badge { font-weight: bold; padding: 4px 10px; border-radius: 4px; font-size: 13px; }
        .counter-ok { background: #133a1b; color: #4ec9b0; border: 1px solid #256631; }
        .counter-err { background: #4a1515; color: #f48771; border: 1px solid #8a2222; }

        .status { color: #4ec9b0; font-weight: bold; margin-left: 10px; }

        .batch-panel { display: flex; align-items: center; gap: 10px; background: #222; padding: 10px 20px; border-radius: 8px; border: 1px solid #333; margin-bottom: 15px; flex-wrap: wrap; }
        .batch-panel label { font-size: 13px; color: #aaa; }
        #batch-size, #start-line { width: 70px; background: #2a2a2a; color: #fff; border: 1px solid #444; padding: 7px 8px; border-radius: 6px; font-size: 14px; }
        #batch-size:focus, #start-line:focus { border-color: #007acc; outline: none; }
        #batch-action-btn { background: #2d7d46; }
        #batch-action-btn:hover { background: #35914f; }
        #batch-action-btn.state-paste { background: #b4740e; }
        #batch-action-btn.state-paste:hover { background: #cf8412; }
        #batch-action-btn.state-done { background: #444; }
        #chunk-status { font-size: 13px; color: #9cdcfe; font-weight: bold; margin-left: auto; }
        #batch-error-msg { font-size: 13px; color: #f48771; font-weight: bold; }
        #batch-error-msg.listening { color: #dcdcaa; }

        .btn-diff { background: #5a3d8c; }
        .btn-diff:hover { background: #6b48a8; }
        .btn-diff.active { background: #8859d6; }

        /* Unified Split Editor & Diff View Container */
        .editor-box {
            display: flex;
            width: 100%;
            height: 73vh;
            background: #1e1e1e;
            border: 1px solid #3c3c3c;
            border-radius: 8px;
            overflow: hidden;
        }

        /* Полная идентичность параметров шрифта и переносов для синхронности */
        textarea, .diff-pane {
            font-family: "Consolas", "Fira Code", "Courier New", monospace;
            font-size: 14px;
            line-height: 22px;
            padding: 15px;
            box-sizing: border-box;
            white-space: pre; /* Отключаем обрезку текста, включаем горизонтальный скролл */
            overflow: auto;
        }

        textarea {
            flex: 1 1 0;
            min-width: 0;
            height: 100%;
            background: transparent;
            color: #9cdcfe;
            border: none;
            resize: none;
        }
        textarea:focus { outline: none; }

        .editor-box.split textarea {
            border-right: 1px solid #3c3c3c;
        }

        .diff-pane {
            display: none;
            flex: 1 1 0;
            min-width: 0;
            height: 100%;
            background: #1e1e1e;
        }
        .editor-box.split .diff-pane { display: block; }

        /* Line-number / character-id gutter. Purely a read-only visual aid:
           it lives outside the <textarea>, so selecting/copying editor text
           never picks up the numbers or ids alongside it. */
        .gutter {
            flex: 0 0 62px;
            height: 100%;
            background: #181818;
            border-right: 1px solid #3c3c3c;
            overflow: hidden;
            box-sizing: border-box;
            padding: 15px 6px 15px 8px;
            font-family: "Consolas", "Fira Code", "Courier New", monospace;
            font-size: 11px;
            line-height: 22px; /* must match textarea/diff-pane for row alignment */
            color: #6a737d;
            user-select: none;
            cursor: default;
        }
        .gutter-row {
            height: 22px;
            line-height: 22px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .gutter-row .g-line { color: #6a737d; }
        .gutter-row .g-char { color: #c586c0; margin-left: 4px; }

        /* Строки diff без обрезок и многоточий */
        .diff-row {
            min-height: 22px;
            line-height: 22px;
            white-space: pre;
            box-sizing: border-box;
        }
        .diff-row.diff-changed { background: rgba(255, 255, 255, 0.03); }
        .diff-row.diff-new { color: #6a9955; background: rgba(106, 153, 85, 0.12); font-style: italic; }
        .diff-row.diff-empty { color: transparent; }
        .diff-seg-equal { color: #999; }
        .diff-seg-delete { color: #f48771; background: rgba(244, 135, 113, 0.18); text-decoration: line-through; text-decoration-color: rgba(244, 135, 113, 0.75); border-radius: 2px; }
        .diff-seg-insert { color: #6a9955; background: rgba(106, 153, 85, 0.2); border-radius: 2px; }
        .diff-status-msg { color: #888; font-style: italic; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="controls">
                <label for="file-select"><b>Файл:</b></label>
                <select id="file-select" onchange="loadFile()"></select>
                <button class="btn-reload" onclick="scanFiles()" title="Обновить список файлов">🔄</button>
            </div>
            <div class="controls" style="max-width: 320px;">
                <label for="commit-select"><b>База Diff:</b></label>
                <select id="commit-select" onchange="onCommitChange()">
                    <option value="HEAD">HEAD (Текущий коммит)</option>
                </select>
            </div>
            <button id="save-btn" onclick="saveData()">Сохранить изменения</button>
            <button id="diff-toggle-btn" class="btn-diff" onclick="toggleDiffView()">🔀 Git Diff</button>
        </div>
        <div class="batch-panel">
            <label for="batch-size">Строк за раз (N):</label>
            <input type="number" id="batch-size" value="100" min="1" step="1" onchange="onBatchSizeChange()">
            <label for="start-line" style="margin-left: 10px;">Начать со строки:</label>
            <input type="number" id="start-line" value="1" min="1" step="1" onchange="onStartLineChange()">
            <button id="batch-action-btn" onclick="handleBatchAction()">Копировать блок</button>
            <span id="batch-error-msg"></span>
            <span id="chunk-status">Блок: - / 0</span>
        </div>
        <div class="info">
            <span>* Одна строка = одна реплика. Изменение количества строк заблокировано.</span>
            <div>
                <span id="line-counter" class="counter-badge counter-ok">Строк: 0 / 0</span>
                <span id="status-msg" class="status"></span>
            </div>
        </div>
        <div class="editor-box" id="editor-box">
            <div class="gutter" id="gutter" title="Номер строки в исходном файле и id персонажа"></div>
            <textarea id="text-editor" oninput="validateLines()" wrap="off" placeholder="Выберите .rpy файл из списка выше..."></textarea>
            <div class="diff-pane" id="diff-pane"></div>
        </div>
    </div>

    <script>
        let originalLineCount = 0;

        let currentIndex = 0;
        let batchState = 'copy';
        let activeBatchLineCount = 0;
        let isListeningForPaste = false;

        let diffViewActive = false;
        let diffData = null;
        let diffLoadedForFile = null;
        let diffLoadedForRef = null;
        let isSyncingScroll = false;

        let gutterMeta = [];

        async function scanFiles() {
            const res = await fetch('/list_files');
            const files = await res.json();
            const select = document.getElementById('file-select');

            select.innerHTML = '';
            if (files.length === 0) {
                select.innerHTML = '<option value="">.rpy файлы не найдены</option>';
                return;
            }

            files.forEach(file => {
                const opt = document.createElement('option');
                opt.value = file;
                opt.textContent = file;
                select.appendChild(opt);
            });

            await loadCommits();
            loadFile();
        }

        async function loadCommits() {
            const res = await fetch('/get_commits');
            const data = await res.json();
            const select = document.getElementById('commit-select');

            select.innerHTML = '<option value="HEAD">HEAD (Текущий коммит)</option>';
            select.innerHTML += '<option value="HEAD~1">HEAD~1 (Преддыдущий коммит)</option>';

            if (data.error) {
                console.warn('get_commits error:', data.error);
                showStatus('Git недоступен: ' + data.error);
            }

            (data.commits || []).forEach(c => {
                if (c.hash !== 'HEAD') {
                    const opt = document.createElement('option');
                    opt.value = c.hash;
                    opt.textContent = `${c.hash} — ${c.subject}`;
                    select.appendChild(opt);
                }
            });
        }

        async function loadFile() {
            const filepath = document.getElementById('file-select').value;
            if (!filepath) return;

            showStatus('Загрузка...');
            const res = await fetch(`/get_data?file=${encodeURIComponent(filepath)}`);
            const data = await res.json();

            document.getElementById('text-editor').value = data.text;
            originalLineCount = data.count;

            gutterMeta = data.meta || [];
            renderGutter();

            currentIndex = 0;
            batchState = 'copy';
            activeBatchLineCount = 0;
            stopPasteListening();
            clearBatchError();
            updateBatchButton();
            updateChunkStatus();

            diffData = null;
            diffLoadedForFile = null;
            diffLoadedForRef = null;
            setDiffViewActive(false);

            validateLines();
            showStatus('Загружено');
        }

        function validateLines() {
            const text = document.getElementById('text-editor').value;
            const currentLines = text ? text.split('\n').length : 0;

            const counterBadge = document.getElementById('line-counter');
            const saveBtn = document.getElementById('save-btn');

            counterBadge.textContent = `Строк: ${currentLines} / ${originalLineCount}`;

            if (currentLines === originalLineCount) {
                counterBadge.className = 'counter-badge counter-ok';
                saveBtn.disabled = false;
                saveBtn.title = '';
            } else {
                counterBadge.className = 'counter-badge counter-err';
                saveBtn.disabled = true;
                const diff = currentLines - originalLineCount;
                const sign = diff > 0 ? '+' : '';
                saveBtn.title = `Нельзя сохранить: количество строк изменилось (${sign}${diff})`;
            }

            updateChunkStatus();

            syncGutterRowCount(currentLines);

            if (diffViewActive) {
                syncDiffPaneRowCount(currentLines);
            }
        }

        function getBatchSize() {
            const el = document.getElementById('batch-size');
            let n = parseInt(el.value, 10);
            if (!n || n < 1) n = 100;
            return n;
        }

        function onBatchSizeChange() {
            updateChunkStatus();
        }

        function onStartLineChange() {
            const el = document.getElementById('start-line');
            let val = parseInt(el.value, 10);
            const total = getEditorLines().length;

            if (isNaN(val) || val < 1) {
                val = 1;
            } else if (val > total && total > 0) {
                val = total;
            }
            el.value = val;

            currentIndex = val - 1;
            batchState = 'copy';
            activeBatchLineCount = 0;
            stopPasteListening();
            clearBatchError();

            updateBatchButton();
            updateChunkStatus();
        }

        function getEditorLines() {
            const text = document.getElementById('text-editor').value;
            return text.length ? text.split('\n') : [];
        }

        function clearBatchError() {
            document.getElementById('batch-error-msg').textContent = '';
        }

        function showBatchError(msg) {
            document.getElementById('batch-error-msg').textContent = msg;
        }

        function updateChunkStatus() {
            const total = getEditorLines().length;
            const statusEl = document.getElementById('chunk-status');
            if (total === 0) {
                statusEl.textContent = 'Блок: - / 0';
                return;
            }

            const startLineEl = document.getElementById('start-line');
            if (startLineEl && document.activeElement !== startLineEl) {
                startLineEl.value = currentIndex + 1;
            }

            if (currentIndex >= total) {
                statusEl.textContent = `Блок: завершено / ${total}`;
                return;
            }
            const n = getBatchSize();
            const end = Math.min(currentIndex + n, total);
            statusEl.textContent = `Блок: ${currentIndex + 1}-${end} / ${total}`;
        }

        function updateBatchButton() {
            const btn = document.getElementById('batch-action-btn');
            btn.classList.remove('state-paste', 'state-done');

            const total = getEditorLines().length;
            if (total === 0) {
                btn.textContent = 'Копировать блок';
                btn.disabled = true;
                return;
            }
            btn.disabled = false;

            if (batchState === 'copy') {
                if (currentIndex >= total) {
                    batchState = 'done';
                    btn.textContent = 'Завершено';
                    btn.classList.add('state-done');
                    btn.disabled = true;
                } else {
                    btn.textContent = 'Копировать блок';
                }
            } else if (batchState === 'paste') {
                btn.textContent = 'Вставить блок';
                btn.classList.add('state-paste');
            } else if (batchState === 'done') {
                btn.textContent = 'Завершено';
                btn.classList.add('state-done');
                btn.disabled = true;
            }
        }

        function handleBatchAction() {
            if (batchState === 'copy') {
                copyBatch();
            } else if (batchState === 'paste') {
                pasteBatch();
            }
        }

        function highlightBatchInEditor(startLine, endLine) {
            const textarea = document.getElementById('text-editor');
            const lines = getEditorLines();

            let startChar = 0;
            for (let i = 0; i < startLine; i++) {
                startChar += lines[i].length + 1;
            }
            let endChar = startChar;
            for (let i = startLine; i < endLine; i++) {
                endChar += lines[i].length + 1;
            }
            endChar = Math.min(endChar - 1, textarea.value.length);

            const savedScrollTop = textarea.scrollTop;
            textarea.focus();
            textarea.setSelectionRange(startChar, Math.max(startChar, endChar));
            textarea.scrollTop = savedScrollTop;
        }

        async function copyBatch() {
            clearBatchError();
            const lines = getEditorLines();
            const total = lines.length;

            if (currentIndex >= total) {
                batchState = 'done';
                updateBatchButton();
                updateChunkStatus();
                return;
            }

            const n = getBatchSize();
            const end = Math.min(currentIndex + n, total);
            const chunkLines = lines.slice(currentIndex, end);
            const chunkText = chunkLines.join('\n');

            try {
                await navigator.clipboard.writeText(chunkText);
            } catch (err) {
                showBatchError('Не удалось скопировать в буфер обмена: ' + err.message);
                return;
            }

            activeBatchLineCount = chunkLines.length;
            highlightBatchInEditor(currentIndex, end);
            showStatus(`Скопировано строк ${currentIndex + 1}-${end}`);

            batchState = 'paste';
            updateBatchButton();
            updateChunkStatus();
        }

        async function pasteBatch() {
            clearBatchError();

            try {
                const clipboardText = await navigator.clipboard.readText();
                applyPastedBatch(clipboardText);
            } catch (err) {
                startPasteListening();
            }
        }

        function startPasteListening() {
            if (isListeningForPaste) return;
            isListeningForPaste = true;
            document.addEventListener('paste', handleGlobalPaste);
            document.addEventListener('keydown', handlePasteListenKeydown);
            const errEl = document.getElementById('batch-error-msg');
            errEl.classList.add('listening');
            errEl.textContent = 'Нажмите Ctrl+V (или Cmd+V), чтобы вставить блок... (Esc — отмена)';
        }

        function stopPasteListening() {
            isListeningForPaste = false;
            document.removeEventListener('paste', handleGlobalPaste);
            document.removeEventListener('keydown', handlePasteListenKeydown);
            document.getElementById('batch-error-msg').classList.remove('listening');
        }

        function handleGlobalPaste(e) {
            e.preventDefault();
            const text = (e.clipboardData || window.clipboardData).getData('text/plain');
            stopPasteListening();
            clearBatchError();
            applyPastedBatch(text);
        }

        function handlePasteListenKeydown(e) {
            if (e.key === 'Escape') {
                stopPasteListening();
                showBatchError('Вставка отменена.');
            }
        }

        function applyPastedBatch(clipboardText) {
            const pastedLines = clipboardText.length ? clipboardText.split(/\r\n|\r|\n/) : [];

            if (pastedLines.length !== activeBatchLineCount) {
                showBatchError(
                    `Несовпадение количества строк: ожидалось ${activeBatchLineCount}, получено ${pastedLines.length}`
                );
                batchState = 'paste';
                updateBatchButton();
                return;
            }

            const lines = getEditorLines();
            const total = lines.length;
            const end = Math.min(currentIndex + activeBatchLineCount, total);

            const newLines = lines.slice(0, currentIndex)
                .concat(pastedLines)
                .concat(lines.slice(end));

            const textarea = document.getElementById('text-editor');
            textarea.value = newLines.join('\n');

            currentIndex = end;
            activeBatchLineCount = 0;
            clearBatchError();
            validateLines();

            if (currentIndex >= newLines.length) {
                batchState = 'done';
                showStatus('Все блоки обработаны!');
            } else {
                batchState = 'copy';
                showStatus('Блок вставлен');
            }

            updateBatchButton();
            updateChunkStatus();
        }

        function setDiffViewActive(active) {
            diffViewActive = active;
            const editorBox = document.getElementById('editor-box');
            const btn = document.getElementById('diff-toggle-btn');
            if (active) {
                editorBox.classList.add('split');
                btn.classList.add('active');
                btn.textContent = '✖ Скрыть Diff';
            } else {
                editorBox.classList.remove('split');
                btn.classList.remove('active');
                btn.textContent = '🔀 Git Diff';
            }
        }

        async function refreshDiffData(filepath) {
            const diffPane = document.getElementById('diff-pane');
            const ref = document.getElementById('commit-select').value;
            const res = await fetch(`/get_diff?file=${encodeURIComponent(filepath)}&ref=${encodeURIComponent(ref)}`);
            const result = await res.json();

            if (!result.available) {
                diffPane.innerHTML = `<div class="diff-status-msg">Git diff недоступен: ${escapeHtml(result.reason || 'неизвестная причина')}</div>`;
                diffData = null;
                diffLoadedForFile = null;
                diffLoadedForRef = null;
                return;
            }

            diffData = result.diff;
            diffLoadedForFile = filepath;
            diffLoadedForRef = ref;

            if (diffViewActive) {
                renderDiffPane();
            }
        }

        async function onCommitChange() {
            const filepath = document.getElementById('file-select').value;
            if (filepath && diffViewActive) {
                const diffPane = document.getElementById('diff-pane');
                diffPane.innerHTML = '<div class="diff-status-msg">Загрузка git diff...</div>';
                await refreshDiffData(filepath);
            }
        }

        async function toggleDiffView() {
            const filepath = document.getElementById('file-select').value;
            if (!filepath) return;

            if (diffViewActive) {
                setDiffViewActive(false);
                return;
            }

            const currentRef = document.getElementById('commit-select').value;
            if (diffLoadedForFile !== filepath || diffLoadedForRef !== currentRef) {
                const diffPane = document.getElementById('diff-pane');
                diffPane.innerHTML = '<div class="diff-status-msg">Загрузка git diff...</div>';
                setDiffViewActive(true);

                await refreshDiffData(filepath);
            } else {
                setDiffViewActive(true);
                renderDiffPane();
            }

            setupScrollSync();
        }

        function escapeHtml(str) {
            const div = document.createElement('div');
            div.textContent = str;
            return div.innerHTML;
        }

        function renderDiffPane() {
            const diffPane = document.getElementById('diff-pane');
            const lineCount = getEditorLines().length;
            diffPane.innerHTML = '';

            if (!diffData) return;

            const frag = document.createDocumentFragment();
            for (let i = 0; i < lineCount; i++) {
                frag.appendChild(buildDiffRow(diffData[i]));
            }
            diffPane.appendChild(frag);
        }

        function buildDiffRow(entry) {
            const row = document.createElement('div');
            row.className = 'diff-row';

            if (!entry) {
                row.classList.add('diff-empty');
                row.textContent = '\u00A0';
            } else if (entry.type === 'changed') {
                row.classList.add('diff-changed');
                if (entry.segments && entry.segments.length) {
                    entry.segments.forEach(seg => {
                        const span = document.createElement('span');
                        span.className = 'diff-seg-' + seg.op;
                        span.textContent = seg.text;
                        row.appendChild(span);
                    });
                } else {
                    row.textContent = '\u00A0';
                }
            } else if (entry.type === 'new') {
                row.classList.add('diff-new');
                row.textContent = '(новая строка)';
            } else {
                row.classList.add('diff-empty');
                row.textContent = '\u00A0';
            }
            return row;
        }

        function syncDiffPaneRowCount(targetCount) {
            const diffPane = document.getElementById('diff-pane');
            const current = diffPane.children.length;

            if (current === targetCount) return;

            if (current < targetCount) {
                const frag = document.createDocumentFragment();
                for (let i = current; i < targetCount; i++) {
                    frag.appendChild(buildDiffRow(diffData ? diffData[i] : null));
                }
                diffPane.appendChild(frag);
            } else {
                for (let i = current - 1; i >= targetCount; i--) {
                    diffPane.removeChild(diffPane.children[i]);
                }
            }
        }

        function buildGutterRow(meta) {
            const row = document.createElement('div');
            row.className = 'gutter-row';

            if (!meta) {
                row.innerHTML = '&nbsp;';
                return row;
            }

            const lineSpan = document.createElement('span');
            lineSpan.className = 'g-line';
            lineSpan.textContent = meta.line;
            row.appendChild(lineSpan);

            if (meta.char) {
                const charSpan = document.createElement('span');
                charSpan.className = 'g-char';
                charSpan.textContent = meta.char;
                row.appendChild(charSpan);
            }

            row.title = meta.char ? `Строка ${meta.line} · ${meta.char}` : `Строка ${meta.line}`;
            return row;
        }

        function renderGutter() {
            const gutter = document.getElementById('gutter');
            gutter.innerHTML = '';

            const frag = document.createDocumentFragment();
            gutterMeta.forEach(meta => frag.appendChild(buildGutterRow(meta)));
            gutter.appendChild(frag);
        }

        function syncGutterRowCount(targetCount) {
            const gutter = document.getElementById('gutter');
            const current = gutter.children.length;

            if (current === targetCount) return;

            if (current < targetCount) {
                const frag = document.createDocumentFragment();
                for (let i = current; i < targetCount; i++) {
                    frag.appendChild(buildGutterRow(i < gutterMeta.length ? gutterMeta[i] : null));
                }
                gutter.appendChild(frag);
            } else {
                for (let i = current - 1; i >= targetCount; i--) {
                    gutter.removeChild(gutter.children[i]);
                }
            }
        }

        let gutterScrollSyncInitialized = false;
        function setupGutterScrollSync() {
            if (gutterScrollSyncInitialized) return;
            gutterScrollSyncInitialized = true;

            const editor = document.getElementById('text-editor');
            const gutter = document.getElementById('gutter');
            let isSyncingGutterScroll = false;

            // Vertical only: the gutter column stays put horizontally even
            // if the (unwrapped) editor text scrolls sideways.
            editor.addEventListener('scroll', () => {
                if (isSyncingGutterScroll) return;
                isSyncingGutterScroll = true;
                gutter.scrollTop = editor.scrollTop;
                isSyncingGutterScroll = false;
            });
        }

        let scrollSyncInitialized = false;
        function setupScrollSync() {
            if (scrollSyncInitialized) return;
            scrollSyncInitialized = true;

            const editor = document.getElementById('text-editor');
            const diffPane = document.getElementById('diff-pane');

            // Синхронизация по обоим осям (X и Y)
            editor.addEventListener('scroll', () => {
                if (isSyncingScroll || !diffViewActive) return;
                isSyncingScroll = true;
                diffPane.scrollTop = editor.scrollTop;
                diffPane.scrollLeft = editor.scrollLeft;
                isSyncingScroll = false;
            });

            diffPane.addEventListener('scroll', () => {
                if (isSyncingScroll || !diffViewActive) return;
                isSyncingScroll = true;
                editor.scrollTop = diffPane.scrollTop;
                editor.scrollLeft = diffPane.scrollLeft;
                isSyncingScroll = false;
            });
        }

        async function saveData() {
            const filepath = document.getElementById('file-select').value;
            const editorText = document.getElementById('text-editor').value;

            if (!filepath) return;

            showStatus('Сохранение...');
            const res = await fetch('/save_data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file: filepath, text: editorText })
            });

            if (res.ok) {
                showStatus('Успешно сохранено!');

                if (diffViewActive || diffLoadedForFile === filepath) {
                    await refreshDiffData(filepath);
                }

                setTimeout(() => showStatus(''), 3000);
            } else {
                const errText = await res.text();
                alert('Ошибка при сохранении: ' + errText);
                showStatus('Ошибка!');
            }
        }

        function showStatus(msg) {
            document.getElementById('status-msg').textContent = msg;
        }

        setupGutterScrollSync();
        scanFiles();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/list_files')
def list_files():
    rpy_files = []
    for root, dirs, files in os.walk(PROJECT_DIR):
        for file in files:
            if file.endswith('.rpy') and not file.endswith('_updated.rpy'):
                rel_path = os.path.relpath(os.path.join(root, file), PROJECT_DIR)
                rpy_files.append(rel_path)

    return jsonify(sorted(rpy_files))

@app.route('/get_commits')
def get_commits():
    ok, reason = is_inside_git_repo()
    if not ok:
        print(f"[get_commits] not a git repo at {PROJECT_DIR}: {reason}")
        return jsonify({'commits': [], 'error': f'Не git-репозиторий ({PROJECT_DIR}): {reason}'})

    try:
        result = subprocess.run(
            ['git', 'log', '-n', '20', '--pretty=format:%h|%s'],
            cwd=PROJECT_DIR, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=5
        )
        if result.returncode != 0:
            print(f"[get_commits] git log failed: {result.stderr}")
            return jsonify({'commits': [], 'error': (result.stderr or 'git log завершился с ошибкой').strip()})

        commits = []
        for line in result.stdout.strip().split('\n'):
            if '|' in line:
                h, msg = line.split('|', 1)
                commits.append({'hash': h, 'subject': msg})
        return jsonify({'commits': commits, 'error': None})
    except FileNotFoundError:
        print("[get_commits] git executable not found in PATH")
        return jsonify({'commits': [], 'error': 'Git не найден в PATH'})
    except Exception as e:
        print(f"[get_commits] unexpected error: {e}")
        return jsonify({'commits': [], 'error': str(e)})

@app.route('/get_data')
def get_data():
    filepath = request.args.get('file', '')
    full_path = os.path.join(PROJECT_DIR, filepath)

    if not os.path.exists(full_path):
        return jsonify({'text': '', 'count': 0, 'meta': []})

    with open(full_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    pure_lines = []
    meta = []
    for line_number, line in enumerate(lines, start=1):
        match = TEXT_PATTERN.match(line)
        if match:
            clean_text = match.group(3).replace('\\"', '"')
            pure_lines.append(clean_text)
            # 'line' is the 1-based line number in the source .rpy file, and
            # 'char' is the character id given explicitly on this line, or
            # 'me' if none is given. Purely for display in the editor's
            # gutter - doesn't affect the plain text in the textarea or on
            # save.
            meta.append({'line': line_number, 'char': match.group(2) or 'me'})

    return jsonify({
        'text': "\n".join(pure_lines),
        'count': len(pure_lines),
        'meta': meta
    })


def extract_pure_lines(raw_text):
    pure_lines = []
    for line in raw_text.splitlines():
        match = TEXT_PATTERN.match(line)
        if match:
            clean_text = match.group(3).replace('\\"', '"')  # Меняем group(2) на group(3)
            pure_lines.append(clean_text)
    return pure_lines

def is_inside_git_repo():
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--is-inside-work-tree'],
            cwd=PROJECT_DIR, capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return True, None
        return False, (result.stderr or 'git rev-parse завершился с ошибкой').strip()
    except FileNotFoundError:
        return False, 'Команда git не найдена (не установлен или не в PATH)'
    except subprocess.SubprocessError as e:
        return False, str(e)


def get_git_revision_text(relpath, ref='HEAD'):
    try:
        normalized_path = relpath.replace('\\', '/')
        if not normalized_path.startswith('./'):
            normalized_path = './' + normalized_path

        result = subprocess.run(
            ['git', 'show', f'{ref}:{normalized_path}'],
            cwd=PROJECT_DIR, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=10
        )
        if result.returncode != 0:
            return None, (result.stderr or f'Файл не найден в ревизии {ref}').strip()
        return result.stdout, None
    except FileNotFoundError:
        return None, 'Git не установлен или недоступен в PATH'
    except subprocess.SubprocessError as e:
        return None, str(e)


@app.route('/get_diff')
def get_diff():
    filepath = request.args.get('file', '')
    ref = request.args.get('ref', 'HEAD')
    full_path = os.path.join(PROJECT_DIR, filepath)

    if not os.path.exists(full_path):
        return jsonify({'available': False, 'reason': 'Файл не найден'})

    repo_ok, repo_reason = is_inside_git_repo()
    if not repo_ok:
        return jsonify({'available': False, 'reason': f'Папка проекта не является git-репозиторием: {repo_reason}'})

    head_content, err = get_git_revision_text(filepath, ref)
    if head_content is None:
        return jsonify({'available': False, 'reason': err})

    with open(full_path, 'r', encoding='utf-8') as f:
        current_content = f.read()

    head_pure = extract_pure_lines(head_content)
    current_pure = extract_pure_lines(current_content)

    matcher = difflib.SequenceMatcher(None, head_pure, current_pure, autojunk=False)
    diff_result = [None] * len(current_pure)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            continue
        elif tag == 'insert':
            for j in range(j1, j2):
                diff_result[j] = {'type': 'new'}
        elif tag == 'replace':
            old_slice = head_pure[i1:i2]
            new_count = j2 - j1
            for k in range(new_count):
                if k < len(old_slice):
                    old_text = old_slice[k]
                    new_text = current_pure[j1 + k]
                    diff_result[j1 + k] = {
                        'type': 'changed',
                        'segments': word_diff_segments(old_text, new_text)
                    }
                else:
                    diff_result[j1 + k] = {'type': 'new'}

    return jsonify({'available': True, 'diff': diff_result, 'count': len(current_pure)})

@app.route('/save_data', methods=['POST'])
def save_data():
    data = request.json
    filepath = data.get('file', '')
    edited_text = data.get('text', '')

    full_path = os.path.join(PROJECT_DIR, filepath)
    edited_lines = edited_text.splitlines()

    if not os.path.exists(full_path):
        return 'File not found', 404

    with open(full_path, 'r', encoding='utf-8') as f:
        rpy_lines = f.readlines()

    orig_text_count = sum(1 for line in rpy_lines if TEXT_PATTERN.match(line))
    if len(edited_lines) != orig_text_count:
        return f'Количество строк не совпадает! Ожидается: {orig_text_count}, получено: {len(edited_lines)}', 400

    output_lines = []
    text_idx = 0

    for line in rpy_lines:
        match = TEXT_PATTERN.match(line)
        if match:
            indent = match.group(1)
            char_tag = f"{match.group(2)} " if match.group(2) else ""  # Сохраняем тег персонажа
            trailing_newline = "\n" if line.endswith('\n') else ""

            new_text = edited_lines[text_idx]
            new_text = new_text.replace('"', '\\"')
            output_lines.append(f'{indent}{char_tag}"{new_text}"{trailing_newline}')
            text_idx += 1
        else:
            output_lines.append(line)

    with open(full_path, 'w', encoding='utf-8') as f:
        f.writelines(output_lines)

    return 'OK', 200

if __name__ == '__main__':
    print(f"Папка проекта: {PROJECT_DIR}")

    found = []
    for root, dirs, files in os.walk(PROJECT_DIR):
        for file in files:
            if file.endswith('.rpy') and not file.endswith('_updated.rpy'):
                found.append(os.path.relpath(os.path.join(root, file), PROJECT_DIR))
    if found:
        print(f"Найдено .rpy файлов: {len(found)} (например: {found[0]})")
    else:
        print("ВНИМАНИЕ: .rpy файлы не найдены в этой папке и её подпапках.")
        print("Укажите правильную папку так:  python RUN.py \"C:\\путь\\к\\проекту\"")

    repo_ok, repo_reason = is_inside_git_repo()
    if repo_ok:
        print("Git-репозиторий: обнаружен.")
    else:
        print(f"Git-репозиторий НЕ обнаружен: {repo_reason}")
        print("Диффы будут недоступны, пока PROJECT_DIR не указывает внутрь git-репозитория.")

    print("Редактор запущен! Откройте браузер: http://127.0.0.1:5000")
    app.run(port=5000)
