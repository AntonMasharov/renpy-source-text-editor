from flask import Flask, render_template_string, request, jsonify
import re
import os
import subprocess
import difflib

app = Flask(__name__)

PROJECT_DIR = os.getcwd()
TEXT_PATTERN = re.compile(r'^(\s*)"([^"\\]*(?:\\.[^"\\]*)*)"(\s*)$')
WORD_TOKEN_PATTERN = re.compile(r'\w+|[^\w\s]|\s+', re.UNICODE)


def tokenize_words(text):
    return WORD_TOKEN_PATTERN.findall(text)


def word_diff_segments(old_text, new_text):
    """Return a GitHub-style inline diff: a list of {'op': 'equal'|'delete'|'insert', 'text': ...}
    segments produced by aligning old_text and new_text word-by-word (not just marking the
    whole line as changed)."""
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

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Редактор сценариев Ren'Py</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #181818; color: #d4d4d4; padding: 20px; margin: 0; }
        .container { max-width: 1000px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; background: #222; padding: 15px 20px; border-radius: 8px; border: 1px solid #333; gap: 15px; }
        .controls { display: flex; align-items: center; gap: 10px; flex-grow: 1; }
        select { background: #2a2a2a; color: #fff; border: 1px solid #444; padding: 8px 12px; border-radius: 6px; font-size: 14px; flex-grow: 1; max-width: 400px; cursor: pointer; }
        select:focus { border-color: #007acc; outline: none; }

        button { background: #0e639c; color: white; border: none; padding: 9px 20px; cursor: pointer; border-radius: 6px; font-weight: bold; font-size: 14px; transition: all 0.2s; white-space: nowrap; }
        button:hover { background: #1177bb; }
        button:disabled { background: #444; color: #888; cursor: not-allowed; }

        .btn-reload { background: #333; }
        .btn-reload:hover { background: #444; }

        .editor-box { position: relative; }
        textarea { width: 100%; height: 73vh; background: #1e1e1e; color: #9cdcfe; border: 1px solid #3c3c3c; padding: 15px; font-size: 16px; line-height: 1.6; border-radius: 8px; box-sizing: border-box; resize: vertical; font-family: inherit; white-space: pre; }
        textarea:focus { border-color: #007acc; outline: none; }

        .info { color: #888; font-size: 13px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }

        /* Стили для счетчика */
        .counter-badge { font-weight: bold; padding: 4px 10px; border-radius: 4px; font-size: 13px; }
        .counter-ok { background: #133a1b; color: #4ec9b0; border: 1px solid #256631; }
        .counter-err { background: #4a1515; color: #f48771; border: 1px solid #8a2222; }

        .status { color: #4ec9b0; font-weight: bold; margin-left: 10px; }

        /* Batch copy/paste controls */
        .batch-panel { display: flex; align-items: center; gap: 10px; background: #222; padding: 10px 20px; border-radius: 8px; border: 1px solid #333; margin-bottom: 15px; flex-wrap: wrap; }
        .batch-panel label { font-size: 13px; color: #aaa; }
        #batch-size { width: 70px; background: #2a2a2a; color: #fff; border: 1px solid #444; padding: 7px 8px; border-radius: 6px; font-size: 14px; }
        #batch-size:focus { border-color: #007acc; outline: none; }
        #batch-action-btn { background: #2d7d46; }
        #batch-action-btn:hover { background: #35914f; }
        #batch-action-btn.state-paste { background: #b4740e; }
        #batch-action-btn.state-paste:hover { background: #cf8412; }
        #batch-action-btn.state-done { background: #444; }
        #chunk-status { font-size: 13px; color: #9cdcfe; font-weight: bold; margin-left: auto; }
        #batch-error-msg { font-size: 13px; color: #f48771; font-weight: bold; }
        #batch-error-msg.listening { color: #dcdcaa; }

        /* Git diff split view */
        .btn-diff { background: #5a3d8c; }
        .btn-diff:hover { background: #6b48a8; }
        .btn-diff.active { background: #8859d6; }

        .editor-box.split { display: flex; gap: 10px; }
        .editor-box.split textarea { width: 50%; flex: 1 1 50%; }

        .diff-pane { display: none; flex: 1 1 50%; height: 73vh; background: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 8px; box-sizing: border-box; padding: 15px; font-size: 16px; line-height: 1.6; font-family: inherit; white-space: pre; overflow: auto; }
        .editor-box.split .diff-pane { display: block; }

        .diff-row { white-space: pre; min-height: 1.6em; }
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
            <button id="save-btn" onclick="saveData()">Сохранить изменения</button>
            <button id="diff-toggle-btn" class="btn-diff" onclick="toggleDiffView()">🔀 Git Diff</button>
        </div>
        <div class="batch-panel">
            <label for="batch-size">Строк за раз (N):</label>
            <input type="number" id="batch-size" value="100" min="1" step="1" onchange="onBatchSizeChange()">
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
            <textarea id="text-editor" oninput="validateLines()" placeholder="Выберите .rpy файл из списка выше..."></textarea>
            <div class="diff-pane" id="diff-pane"></div>
        </div>
    </div>

    <script>
        let originalLineCount = 0;

        // --- Batch copy/paste state ---
        let currentIndex = 0;          // start line (0-based) of active chunk
        let batchState = 'copy';       // 'copy' | 'paste' | 'done'
        let activeBatchLineCount = 0;  // number of lines in the currently-copied batch
        let isListeningForPaste = false; // true while waiting for a native Ctrl+V after clipboard.readText() failed

        // --- Git diff view state ---
        let diffViewActive = false;
        let diffData = null;       // array parallel to current lines: null | {type:'changed', old} | {type:'new'}
        let diffLoadedForFile = null;
        let isSyncingScroll = false;

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

            loadFile();
        }

        async function loadFile() {
            const filepath = document.getElementById('file-select').value;
            if (!filepath) return;

            showStatus('Загрузка...');
            const res = await fetch(`/get_data?file=${encodeURIComponent(filepath)}`);
            const data = await res.json();

            document.getElementById('text-editor').value = data.text;
            originalLineCount = data.count;

            // Reset batch cursor/state on (re)load
            currentIndex = 0;
            batchState = 'copy';
            activeBatchLineCount = 0;
            stopPasteListening();
            clearBatchError();
            updateBatchButton();
            updateChunkStatus();

            // Reset diff view state on (re)load — the diff must be re-fetched for the new file
            diffData = null;
            diffLoadedForFile = null;
            setDiffViewActive(false);

            validateLines();
            showStatus('Загружено');
        }

        // Подсчет и валидация строк в реальном времени
        function validateLines() {
            const text = document.getElementById('text-editor').value;
            // Разбиваем текст по переносам строк
            const currentLines = text ? text.split('\\n').length : 0;

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

            if (diffViewActive) {
                syncDiffPaneRowCount(currentLines);
            }
        }

        // ================= Batch Copy/Paste =================

        function getBatchSize() {
            const el = document.getElementById('batch-size');
            let n = parseInt(el.value, 10);
            if (!n || n < 1) n = 100;
            return n;
        }

        function onBatchSizeChange() {
            // Changing N mid-flow only affects the *next* batch; just refresh the status label.
            updateChunkStatus();
        }

        function getEditorLines() {
            const text = document.getElementById('text-editor').value;
            return text.length ? text.split('\\n') : [];
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
            // Select the corresponding text range in the textarea (best-effort, char offsets)
            const textarea = document.getElementById('text-editor');
            const lines = getEditorLines();

            let startChar = 0;
            for (let i = 0; i < startLine; i++) {
                startChar += lines[i].length + 1; // +1 for the newline
            }
            let endChar = startChar;
            for (let i = startLine; i < endLine; i++) {
                endChar += lines[i].length + 1;
            }
            endChar = Math.min(endChar - 1, textarea.value.length); // trim trailing newline

            textarea.focus();
            textarea.setSelectionRange(startChar, Math.max(startChar, endChar));
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
            const end = Math.min(currentIndex + n, total); // handles end-of-file gracefully
            const chunkLines = lines.slice(currentIndex, end);
            const chunkText = chunkLines.join('\\n');

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
                // Permission denied / unsupported (e.g. non-HTTPS, or the site hasn't
                // been granted clipboard-read permission). Stay on this same page and
                // just listen for the user's next native Ctrl+V / Cmd+V instead of
                // opening any separate window or dialog.
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
            const pastedLines = clipboardText.length ? clipboardText.split(/\\r\\n|\\r|\\n/) : [];

            if (pastedLines.length !== activeBatchLineCount) {
                showBatchError(
                    `Несовпадение количества строк: ожидалось ${activeBatchLineCount}, получено ${pastedLines.length}`
                );
                // Stay in 'paste' state so the user can fix the clipboard and retry
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
            textarea.value = newLines.join('\\n');

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

        // ================= End Batch Copy/Paste =================

        // ================= Git Diff View =================

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

        async function toggleDiffView() {
            const filepath = document.getElementById('file-select').value;
            if (!filepath) return;

            if (diffViewActive) {
                setDiffViewActive(false);
                return;
            }

            // Need fresh diff data if we haven't loaded it for this file yet
            if (diffLoadedForFile !== filepath) {
                const diffPane = document.getElementById('diff-pane');
                diffPane.innerHTML = '<div class="diff-status-msg">Загрузка git diff...</div>';
                setDiffViewActive(true);

                const res = await fetch(`/get_diff?file=${encodeURIComponent(filepath)}`);
                const result = await res.json();

                if (!result.available) {
                    diffPane.innerHTML = `<div class="diff-status-msg">Git diff недоступен: ${escapeHtml(result.reason || 'неизвестная причина')}</div>`;
                    diffData = null;
                    diffLoadedForFile = null;
                    return;
                }

                diffData = result.diff;
                diffLoadedForFile = filepath;
            } else {
                setDiffViewActive(true);
            }

            renderDiffPane();
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

        // Keep the diff pane's row count matching the editor's current line count
        // (e.g. while the user is mid-edit and briefly has an unequal count).
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

        let scrollSyncInitialized = false;
        function setupScrollSync() {
            if (scrollSyncInitialized) return;
            scrollSyncInitialized = true;

            const editor = document.getElementById('text-editor');
            const diffPane = document.getElementById('diff-pane');

            editor.addEventListener('scroll', () => {
                if (isSyncingScroll || !diffViewActive) return;
                isSyncingScroll = true;
                diffPane.scrollTop = editor.scrollTop;
                isSyncingScroll = false;
            });

            diffPane.addEventListener('scroll', () => {
                if (isSyncingScroll || !diffViewActive) return;
                isSyncingScroll = true;
                editor.scrollTop = diffPane.scrollTop;
                isSyncingScroll = false;
            });
        }

        // ================= End Git Diff View =================

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

@app.route('/get_data')
def get_data():
    filepath = request.args.get('file', '')
    full_path = os.path.join(PROJECT_DIR, filepath)

    if not os.path.exists(full_path):
        return jsonify({'text': '', 'count': 0})

    with open(full_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    pure_lines = []
    for line in lines:
        match = TEXT_PATTERN.match(line)
        if match:
            clean_text = match.group(2).replace('\\"', '"')
            pure_lines.append(clean_text)

    # Возвращаем и текст, и ИСХОДНОЕ количество текстовых строк
    return jsonify({
        'text': "\n".join(pure_lines),
        'count': len(pure_lines)
    })


def extract_pure_lines(raw_text):
    """Extract translatable text lines the same way get_data does, from raw file content."""
    pure_lines = []
    for line in raw_text.splitlines():
        match = TEXT_PATTERN.match(line)
        if match:
            clean_text = match.group(2).replace('\\"', '"')
            pure_lines.append(clean_text)
    return pure_lines


def is_inside_git_repo():
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--is-inside-work-tree'],
            cwd=PROJECT_DIR, capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


def get_git_head_text(relpath):
    """Return (content, error) for the HEAD-committed version of relpath."""
    try:
        # Git expects paths relative to the repository root when queried with HEAD:<path>,
        # but supports HEAD:./<path> to query relative to the current working directory.
        # We replace backslashes with forward slashes for Git path compatibility.
        normalized_path = relpath.replace('\\', '/')
        if not normalized_path.startswith('./'):
            normalized_path = './' + normalized_path

        result = subprocess.run(
            ['git', 'show', f'HEAD:{normalized_path}'],
            cwd=PROJECT_DIR, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=10
        )
        if result.returncode != 0:
            return None, (result.stderr or 'Файл не найден в последнем коммите (HEAD)').strip()
        return result.stdout, None
    except FileNotFoundError:
        return None, 'Git не установлен или недоступен в PATH'
    except subprocess.SubprocessError as e:
        return None, str(e)


@app.route('/get_diff')
def get_diff():
    filepath = request.args.get('file', '')
    full_path = os.path.join(PROJECT_DIR, filepath)

    if not os.path.exists(full_path):
        return jsonify({'available': False, 'reason': 'Файл не найден'})

    if not is_inside_git_repo():
        return jsonify({'available': False, 'reason': 'Папка проекта не является git-репозиторием'})

    head_content, err = get_git_head_text(filepath)
    if head_content is None:
        return jsonify({'available': False, 'reason': err})

    with open(full_path, 'r', encoding='utf-8') as f:
        current_content = f.read()

    head_pure = extract_pure_lines(head_content)
    current_pure = extract_pure_lines(current_content)

    # Align HEAD lines to current (working-tree) lines and figure out, for each
    # CURRENT line, whether it's unchanged, changed (with the old HEAD text), or new.
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
        # 'delete' opcodes remove HEAD-only lines that have no counterpart
        # in the current file, so there is no current row to attach them to.

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

    # Дополнительная серверная проверка безопасности
    orig_text_count = sum(1 for line in rpy_lines if TEXT_PATTERN.match(line))
    if len(edited_lines) != orig_text_count:
        return f'Количество строк не совпадает! Ожидается: {orig_text_count}, получено: {len(edited_lines)}', 400

    output_lines = []
    text_idx = 0

    for line in rpy_lines:
        match = TEXT_PATTERN.match(line)
        if match:
            indent = match.group(1)
            trailing_newline = "\n" if line.endswith('\n') else ""

            new_text = edited_lines[text_idx]
            new_text = new_text.replace('"', '\\"')
            output_lines.append(f'{indent}"{new_text}"{trailing_newline}')
            text_idx += 1
        else:
            output_lines.append(line)

    with open(full_path, 'w', encoding='utf-8') as f:
        f.writelines(output_lines)

    return 'OK', 200

if __name__ == '__main__':
    print("Редактор запущен! Откройте браузер: http://127.0.0.1:5000")
    app.run(port=5000)
