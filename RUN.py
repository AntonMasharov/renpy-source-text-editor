from flask import Flask, render_template_string, request, jsonify
import re
import os

app = Flask(__name__)

PROJECT_DIR = os.getcwd()
TEXT_PATTERN = re.compile(r'^(\s*)"([^"\\]*(?:\\.[^"\\]*)*)"(\s*)$')

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
        </div>
        <div class="info">
            <span>* Одна строка = одна реплика. Изменение количества строк заблокировано.</span>
            <div>
                <span id="line-counter" class="counter-badge counter-ok">Строк: 0 / 0</span>
                <span id="status-msg" class="status"></span>
            </div>
        </div>
        <div class="editor-box">
            <textarea id="text-editor" oninput="validateLines()" placeholder="Выберите .rpy файл из списка выше..."></textarea>
        </div>
    </div>

    <script>
        let originalLineCount = 0;

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
