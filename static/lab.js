const button = document.getElementById('run');
const input = document.getElementById('question');
const status = document.getElementById('status');
const sections = document.getElementById('sections');

function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = String(text);
    if (className) node.className = className;
    return node;
}

function drawGraph(graph, container) {
    const namespace = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(namespace, 'svg');
    svg.classList.add('graph');
    svg.setAttribute('viewBox', '0 0 640 310');
    const nodes = (graph.nodes || []).slice(0, 18);
    const positions = new Map();
    nodes.forEach((node, index) => {
        const angle = 2 * Math.PI * index / Math.max(nodes.length, 1);
        positions.set(String(node.id), [320 + 225 * Math.cos(angle), 155 + 105 * Math.sin(angle)]);
    });
    (graph.edges || []).forEach(edge => {
        const start = positions.get(String(edge.source));
        const end = positions.get(String(edge.target));
        if (!start || !end) return;
        const line = document.createElementNS(namespace, 'line');
        line.setAttribute('x1', start[0]); line.setAttribute('y1', start[1]);
        line.setAttribute('x2', end[0]); line.setAttribute('y2', end[1]);
        svg.append(line);
    });
    nodes.forEach(node => {
        const [x, y] = positions.get(String(node.id));
        const circle = document.createElementNS(namespace, 'circle');
        circle.setAttribute('cx', x); circle.setAttribute('cy', y); circle.setAttribute('r', 7);
        const label = document.createElementNS(namespace, 'text');
        label.setAttribute('x', x); label.setAttribute('y', y - 13); label.setAttribute('text-anchor', 'middle');
        label.textContent = node.label || node.id;
        svg.append(circle, label);
    });
    container.append(svg);
}

function render(data) {
    document.getElementById('empty').hidden = true;
    document.getElementById('empty').style.display = 'none';
    document.getElementById('output').hidden = false;
    document.getElementById('summary').textContent = data.summary || '';
    const metrics = document.getElementById('metrics');
    metrics.replaceChildren();
    Object.entries(data.metrics || {}).forEach(([key, value]) => {
        const card = element('div', undefined, 'metric');
        card.append(element('div', key, 'metric-key'), element('div', value, 'metric-value'));
        metrics.append(card);
    });
    sections.replaceChildren();
    (data.sections || []).forEach(section => {
        const block = element('section', undefined, 'result-section');
        block.append(element('h3', section.title));
        if (section.text) block.append(element('p', section.text));
        if (section.items) {
            const list = element('ul');
            section.items.forEach(item => list.append(element('li', typeof item === 'object' ? JSON.stringify(item) : item)));
            block.append(list);
        }
        if (section.table) {
            const wrapper = element('div', undefined, 'table-wrap');
            const table = element('table');
            const head = element('thead');
            const heading = element('tr');
            section.table.columns.forEach(column => heading.append(element('th', column)));
            head.append(heading);
            const body = element('tbody');
            section.table.rows.forEach(row => {
                const tr = element('tr');
                row.forEach(value => tr.append(element('td', typeof value === 'object' ? JSON.stringify(value) : value)));
                body.append(tr);
            });
            table.append(head, body); wrapper.append(table); block.append(wrapper);
        }
        if (section.graph) drawGraph(section.graph, block);
        sections.append(block);
    });
    document.getElementById('raw').textContent = JSON.stringify(data, null, 2);
    const execution = data.execution || {};
    document.getElementById('execution-label').textContent = `${execution.mode === 'live' ? 'API' : 'LOCAL'} · ${execution.duration_ms} ms`;
}

document.getElementById('example').addEventListener('click', event => {
    input.value = event.currentTarget.dataset.sample;
});

button.addEventListener('click', async () => {
    const text = input.value.trim();
    if (!text) { status.textContent = '请先输入问题。'; return; }
    const mode = document.querySelector('input[name="mode"]:checked').value;
    button.disabled = true;
    document.getElementById('output').hidden = true;
    document.getElementById('empty').style.display = 'flex';
    status.classList.remove('error');
    status.textContent = mode === 'live' ? '正在连接已配置的模型服务……' : '正在运行本地算法……';
    try {
        const response = await fetch('api/run', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text, mode})});
        const data = await response.json();
        if (!response.ok) {
            const attempts = data.execution?.api_attempts || 0;
            throw new Error((data.error || '运行失败') + (attempts ? ` 本次已尝试 ${attempts} 次 API 调用。` : ''));
        }
        render(data);
        status.textContent = mode === 'live' ? '云端运行完成，实际 API 调用信息见 JSON。' : '本地算法运行完成，本次未请求云端模型。';
    } catch (error) {
        status.classList.add('error');
        status.textContent = error.message || '连接失败，请检查运行窗口。';
    } finally {
        button.disabled = false;
    }
});
