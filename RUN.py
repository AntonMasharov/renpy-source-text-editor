from flask import Flask, render_template_string, request, jsonify
import re
import os

app = Flask(__name__)
RPY_FILE = 'script.rpy'

# Регулярка для поиска текста в кавычках
TEXT_PATTERN = re.compile(r'^(\s*)"([^"\\]*(?:\\.[^"\\]*)*)"(\s*)$')

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Редактор сценария Ren'Py</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #181818; color: #d4d4d4; padding: 20px; margin: 0; }
        .container { max-width: 900px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; background: #222; padding: 15px 20px; border-radius: 8px; border: 1px solid #333; }
        h2 { margin: 0; font-size: 20px; }
        button { background: #0e639c; color: white; border: none; padding: 10px 24px; cursor: pointer; border-radius: 6px; font-weight: bold; font-size: 14px; transition: background 0.2s; }
        button:hover { background: #1177bb; }
        .editor-box { position: relative; }
        textarea { width: 100%; height: 75vh; background: #1e1e1e; color: #9cdcfe; border: 1px solid #3c3c3c; padding: 15px; font-size: 16px; line-height: 1.6; border-radius: 8px; box-sizing: border-box; resize: vertical; font-family: inherit; white-space: pre; }
        textarea:focus { border-color: #007acc; outline: none; }
        .info { color: #888; font-size: 13px; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>Редактор текста (Чистый сценарий)</h2>
            <button onclick="saveData()">Сохранить изменения</button>
        </div>
        <div class="info">
            * Каждая строка ниже — это отдельная реплика. Не удаляйте и не добавляйте пустые строки, чтобы не сбить привязку к сценам и музыке.
        </div>
        <div class="editor-box">
            <textarea id="text-editor" placeholder="Загрузка текста..."></textarea>
        </div>
    </div>

    <script>
        // Загрузка сплошного текста
        async function loadData() {
            const res = await fetch('/get_data');
            const text = await res.text();
            document.getElementById('text-editor').value = text;
        }

        // Сохранение изменений
        async function saveData() {
            const editorText = document.getElementById('text-editor').value;

            const res = await fetch('/save_data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: editorText })
            });

            if (res.ok) alert('Изменения успешно сохранены в script.rpy!');
            else alert('Ошибка при сохранении!');
        }

        loadData();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/get_data')
def get_data():
    if not os.path.exists(RPY_FILE):
        return ""

    with open(RPY_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    pure_lines = []
    for line in lines:
        match = TEXT_PATTERN.match(line)
        if match:
            # Убираем экранированные кавычки для удобства чтения
            clean_text = match.group(2).replace('\\"', '"')
            pure_lines.append(clean_text)

    # Возвращаем сплошной текст (строка за строкой)
    return "\n".join(pure_lines)

@app.route('/save_data', methods=['POST'])
def save_data():
    edited_text = request.json.get('text', '')
    # Разбиваем пришедший текст обратно на список строк
    edited_lines = edited_text.splitlines()

    if not os.path.exists(RPY_FILE):
        return 'File not found', 404

    with open(RPY_FILE, 'r', encoding='utf-8') as f:
        rpy_lines = f.readlines()

    output_lines = []
    text_idx = 0

    for line in rpy_lines:
        match = TEXT_PATTERN.match(line)
        if match:
            indent = match.group(1)
            # Сохраняем оригинальные переносы строк без создания пустых
            trailing_newline = "\n" if line.endswith('\n') else ""

            if text_idx < len(edited_lines):
                new_text = edited_lines[text_idx]
                # Возвращаем экранирование кавычек
                new_text = new_text.replace('"', '\\"')
                output_lines.append(f'{indent}"{new_text}"{trailing_newline}')
                text_idx += 1
            else:
                output_lines.append(line)
        else:
            # Служебные команды (scene, play, with) сохраняются 1 в 1
            output_lines.append(line)

    with open(RPY_FILE, 'w', encoding='utf-8') as f:
        f.writelines(output_lines)

    return 'OK', 200

if __name__ == '__main__':
    print("Откройте браузер: http://127.0.0.1:5000")
    app.run(port=5000)
