(() => {
    'use strict';
    const charts = JSON.parse(document.getElementById('chart-data').textContent);
    const NS = 'http://www.w3.org/2000/svg';
    const colors = ['#1377bd', '#d66c16', '#239278', '#a254b5', '#c1425a', '#668329', '#675fc1', '#087f91'];
    const finite = value => typeof value === 'number' && Number.isFinite(value);
    const fmt = value => {
        if (!finite(value)) {
            return '不可用';
        }
        if (value === 0) {
            return '0';
        }
        return Number(value.toPrecision(6)).toString();
    };

    function element(tag, text, parent, attributes = {}) {
        const el = document.createElement(tag);
        if (text != null) {
            el.textContent = text;
        }
        Object.entries(attributes).forEach(([key, value]) => el.setAttribute(key, value));
        if (parent) {
            parent.append(el);
        }
        return el;
    }

    function svgElement(tag, attributes, parent, text) {
        const el = document.createElementNS(NS, tag);
        Object.entries(attributes).forEach(([key, value]) => el.setAttribute(key, value));
        if (text != null) {
            el.textContent = text;
        }
        parent.append(el);
        return el;
    }

    const metrics = [
        ['normalized_error.max', '最大归一化误差 / %'],
        ['normalized_error.mean', '平均归一化误差 / %'],
        ['normalized_error.rms', 'RMS 归一化误差 / %'],
        ['absolute_error.max', '最大绝对误差'],
        ['absolute_error.mean', '平均绝对误差'],
        ['absolute_error.rms', 'RMS 绝对误差']
    ];

    class Chart {
        constructor(data) {
            this.data = data;
            this.hidden = new Set();
            this.log = false;
            this.mode = 'zoom';
            this.metric = 'normalized_error.max';
            this.box = {
                left: 108,
                top: 24,
                width: 870,
                height: 326
            };
            this.card = element('article', null, document.getElementById('chart-list'), {
                class: 'chart',
                id: data.id
            });
            element('h3', data.title, this.card);
            element('p', data.description, this.card, {
                class: 'chart-subtitle'
            });
            const bar = element('div', null, this.card, {
                class: 'toolbar',
                role: 'group',
                'aria-label': '图表操作'
            });
            this.button(bar, '放大 +', () => this.zoom(.7));
            this.button(bar, '缩小 −', () => this.zoom(1 / .7));
            this.button(bar, '重置', () => this.reset());
            this.pan = this.button(bar, '平移', () => {
                this.mode = this.mode === 'zoom' ? 'pan' : 'zoom';
                this.pan.setAttribute('aria-pressed', String(this.mode === 'pan'));
                this.svg.style.cursor = this.mode === 'pan' ? 'grab' : 'crosshair';
            });
            this.pan.setAttribute('aria-pressed', 'false');
            const axis = element('label', 'Y 轴', bar);
            const select = element('select', null, axis, {
                'aria-label': 'Y 轴刻度'
            });
            element('option', '线性', select, {
                value: 'linear'
            });
            element('option', '对数', select, {
                value: 'log'
            });
            select.onchange = () => {
                this.log = select.value === 'log';
                this.reset();
            };
            if (data.kind === 'field') {
                const metric = element('select', null, bar, {
                    'aria-label': '误差统计量'
                });
                metrics.forEach(([key, text]) => element('option', text, metric, {
                    value: key
                }));
                metric.onchange = () => {
                    this.metric = metric.value;
                    this.reset();
                };
            }
            this.button(bar, '全屏', async () => {
                try {
                    if (document.fullscreenElement) {
                        await document.exitFullscreen();
                    } else {
                        await this.card.requestFullscreen();
                    }
                } catch (error) {
                    this.note.textContent = '浏览器未允许全屏，可使用浏览器窗口最大化。';
                }
            });
            this.button(bar, '导出当前 SVG', () => this.download());
            this.plot = element('div', null, this.card, {
                class: 'plot'
            });
            this.svg = document.createElementNS(NS, 'svg');
            this.svg.setAttribute('viewBox', '0 0 1040 414');
            this.svg.setAttribute('role', 'img');
            this.svg.setAttribute('aria-label', data.title);
            this.svg.style.cursor = 'crosshair';
            this.plot.append(this.svg);
            this.tip = element('div', null, this.plot, {
                class: 'tooltip',
                role: 'status'
            });
            this.note = element('p', null, this.card, {
                class: 'chart-note'
            });
            const legend = element('div', null, this.card, {
                class: 'legend',
                'aria-label': '曲线显隐'
            });
            data.series.forEach((series, index) => {
                const button = this.button(legend, '', () => {
                    if (this.hidden.has(index)) {
                        this.hidden.delete(index);
                    } else {
                        this.hidden.add(index);
                    }
                    button.setAttribute('aria-pressed', String(!this.hidden.has(index)));
                    this.reset();
                });
                button.setAttribute('aria-pressed', 'true');
                button.title = series.job_id;
                const swatch = element('span', null, button, {
                    class: 'swatch'
                });
                swatch.style.background = colors[index % colors.length];
                element('span', series.label, button);
            });
            this.svg.addEventListener('wheel', event => {
                event.preventDefault();
                const point = this.position(event);
                if (this.inside(point)) {
                    this.zoom(event.deltaY > 0 ? 1.2 : 1 / 1.2, point);
                }
            }, {
                passive: false
            });
            this.svg.addEventListener('dblclick', () => this.reset());
            this.svg.addEventListener('pointerdown', event => this.start(event));
            this.svg.addEventListener('pointermove', event => this.move(event));
            this.svg.addEventListener('pointerup', event => this.end(event));
            this.svg.addEventListener('pointercancel', () => {
                this.drag = null;
                this.draw();
            });
            this.svg.addEventListener('pointerleave', () => {
                if (!this.drag) {
                    this.tip.style.display = 'none';
                }
            });
            this.reset();
        }

        button(parent, text, callback) {
            const button = element('button', text, parent, {
                type: 'button'
            });
            button.onclick = callback;
            return button;
        }

        value(point) {
            return point.metrics ? point.metrics[this.metric] : point.y;
        }

        transformed(point) {
            const y = this.value(point);
            if (!finite(y)) {
                return null;
            }
            if (this.log) {
                if (y <= 0) {
                    return null;
                }
                return Math.log10(y);
            }
            return y;
        }

        bounds() {
            const xs = [],
                ys = [];
            this.data.series.forEach((series, i) => {
                if (this.hidden.has(i)) {
                    return;
                }
                series.points.forEach(point => {
                    if (finite(point.x)) {
                        xs.push(point.x);
                    }
                    const y = this.transformed(point);
                    if (finite(y) && finite(point.x)) {
                        ys.push(y);
                    }
                });
            });
            const range = (values, yAxis) => {
                if (!values.length) {
                    return [0, 1];
                }
                let low = Infinity,
                    high = -Infinity;
                values.forEach(value => {
                    low = Math.min(low, value);
                    high = Math.max(high, value);
                });
                let minimum = 0;
                if (yAxis) {
                    if (this.log) {
                        minimum = .1;
                    } else {
                        minimum = Math.max(Math.abs(low), Math.abs(high)) * .1 || 1;
                    }
                } else if (high === low) {
                    minimum = 1;
                }
                const span = Math.max(high - low, minimum);
                const center = (low + high) / 2;
                return [center - span * .55, center + span * .55];
            };
            return [...range(xs, false), ...range(ys, true)];
        }

        reset() {
            this.view = this.bounds();
            this.drag = null;
            this.draw();
        }

        map(x, y) {
            const b = this.box,
                v = this.view;
            return [b.left + (x - v[0]) / (v[1] - v[0]) * b.width, b.top + b.height - (y - v[2]) / (v[3] - v[2]) * b.height];
        }

        unmap(point, view = this.view) {
            const b = this.box;
            return [view[0] + (point[0] - b.left) / b.width * (view[1] - view[0]), view[3] - (point[1] - b.top) / b.height * (view[3] - view[2])];
        }

        position(event) {
            const p = this.svg.createSVGPoint();
            p.x = event.clientX;
            p.y = event.clientY;
            const local = p.matrixTransform(this.svg.getScreenCTM().inverse());
            return [local.x, local.y];
        }

        inside(p) {
            const b = this.box;
            return p[0] >= b.left && p[0] <= b.left + b.width && p[1] >= b.top && p[1] <= b.top + b.height;
        }

        clamp(p) {
            const b = this.box;
            return [Math.max(b.left, Math.min(b.left + b.width, p[0])), Math.max(b.top, Math.min(b.top + b.height, p[1]))];
        }

        zoom(factor, point) {
            const b = this.box,
                v = this.view,
                center = this.unmap(point || [b.left + b.width / 2, b.top + b.height / 2]);
            const next = v.map((value, i) => center[i < 2 ? 0 : 1] + (value - center[i < 2 ? 0 : 1]) * factor);
            if (next.every(finite) && next[1] > next[0] && next[3] > next[2]) {
                this.view = next;
                this.draw();
            }
        }

        start(event) {
            if (event.button !== 0) {
                return;
            }
            const point = this.position(event);
            if (!this.inside(point)) {
                return;
            }
            event.preventDefault();
            this.svg.setPointerCapture(event.pointerId);
            this.drag = {
                start: point,
                view: this.view.slice()
            };
            this.tip.style.display = 'none';
        }

        move(event) {
            const point = this.clamp(this.position(event));
            if (!this.drag) {
                if (this.inside(this.position(event))) {
                    this.hover(point);
                }
                return;
            }
            const start = this.drag.start;
            if (this.mode === 'pan') {
                const before = this.unmap(start, this.drag.view),
                    after = this.unmap(point, this.drag.view);
                this.view = this.drag.view.map((value, i) => value + before[i < 2 ? 0 : 1] - after[i < 2 ? 0 : 1]);
                this.draw();
            } else {
                this.selection.setAttribute('x', Math.min(start[0], point[0]));
                this.selection.setAttribute('y', Math.min(start[1], point[1]));
                this.selection.setAttribute('width', Math.abs(start[0] - point[0]));
                this.selection.setAttribute('height', Math.abs(start[1] - point[1]));
            }
        }

        end(event) {
            if (!this.drag) {
                return;
            }
            const point = this.clamp(this.position(event)),
                start = this.drag.start;
            if (this.mode === 'zoom' && Math.abs(start[0] - point[0]) > 5 && Math.abs(start[1] - point[1]) > 5) {
                const a = this.unmap(start),
                    b = this.unmap(point);
                this.view = [Math.min(a[0], b[0]), Math.max(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[1], b[1])];
            }
            this.drag = null;
            this.svg.releasePointerCapture(event.pointerId);
            this.draw();
        }

        hover(point) {
            let best = null,
                distance = Infinity;
            this.data.series.forEach((series, index) => {
                if (this.hidden.has(index)) {
                    return;
                }
                series.points.forEach(p => {
                    const y = this.transformed(p);
                    if (!finite(p.x) || !finite(y)) {
                        return;
                    }
                    const mapped = this.map(p.x, y);
                    if (!this.inside(mapped)) {
                        return;
                    }
                    const d = (mapped[0] - point[0]) ** 2 + (mapped[1] - point[1]) ** 2;
                    if (d < distance) {
                        distance = d;
                        best = {
                            series,
                            p,
                            mapped
                        };
                    }
                });
            });
            if (!best || distance > 6400) {
                this.tip.style.display = 'none';
                return;
            }
            this.tip.textContent = best.series.label + '\n作业：' + best.series.job_id + '\n' + this.data.xlabel + ': ' + best.p.x + '\n' + this.yLabel() + ': ' + this.value(best.p) + (best.p.step != null ? '\nStep: ' + best.p.step : '');
            this.tip.style.display = 'block';
            this.tip.style.left = Math.min(best.mapped[0] / 1040 * 100, 55) + '%';
            this.tip.style.top = Math.max(0, best.mapped[1] / 414 * 100 - 22) + '%';
        }

        yLabel() {
            if (this.data.kind !== 'field') {
                return this.data.ylabel;
            }
            let label = metrics.find(item => item[0] === this.metric)[1];
            if (this.metric.startsWith('absolute')) {
                label += ' [' + this.data.unit + ']';
            }
            return label;
        }

        draw() {
            this.svg.replaceChildren();
            this.tip.style.display = 'none';
            this.svg.dataset.view = JSON.stringify(this.view);
            const b = this.box,
                v = this.view;
            svgElement('rect', {
                width: 1040,
                height: 414,
                fill: '#fff'
            }, this.svg);
            const defs = svgElement('defs', {}, this.svg),
                clip = svgElement('clipPath', {
                    id: this.data.id + '-clip'
                }, defs);
            svgElement('rect', {
                x: b.left,
                y: b.top,
                width: b.width,
                height: b.height
            }, clip);
            const textStyle = {
                'font-family': 'Segoe UI,Microsoft YaHei,sans-serif',
                'font-size': 12,
                fill: '#4d6275'
            };
            for (let i = 0; i <= 5; i++) {
                const x = b.left + i * b.width / 5,
                    y = b.top + i * b.height / 5;
                svgElement('line', {
                    x1: x,
                    y1: b.top,
                    x2: x,
                    y2: b.top + b.height,
                    stroke: '#e2e9ef'
                }, this.svg);
                svgElement('line', {
                    x1: b.left,
                    y1: y,
                    x2: b.left + b.width,
                    y2: y,
                    stroke: '#e2e9ef'
                }, this.svg);
                svgElement('text', {
                    ...textStyle,
                    x,
                    y: b.top + b.height + 23,
                    'text-anchor': 'middle'
                }, this.svg, fmt(v[0] + i * (v[1] - v[0]) / 5));
                const value = v[3] - i * (v[3] - v[2]) / 5;
                svgElement('text', {
                    ...textStyle,
                    x: b.left - 10,
                    y: y + 4,
                    'text-anchor': 'end'
                }, this.svg, fmt(this.log ? 10 ** value : value));
            }
            svgElement('text', {
                ...textStyle,
                x: b.left + b.width / 2,
                y: 402,
                'text-anchor': 'middle'
            }, this.svg, this.data.xlabel);
            svgElement('text', {
                ...textStyle,
                transform: 'translate(19 187) rotate(-90)',
                'text-anchor': 'middle'
            }, this.svg, this.yLabel() + (this.log ? ' (log)' : ''));
            const group = svgElement('g', {
                'clip-path': 'url(#' + this.data.id + '-clip)'
            }, this.svg);
            let invalid = 0,
                nonpositive = 0,
                count = 0,
                drawn = 0;
            this.data.series.forEach((series, index) => {
                if (this.hidden.has(index)) {
                    return;
                }
                let d = '',
                    pen = false,
                    last = null;
                series.points.forEach(point => {
                    count++;
                    const value = this.value(point),
                        y = this.transformed(point);
                    if (!finite(point.x) || !finite(value)) {
                        invalid++;
                        pen = false;
                        last = null;
                        return;
                    }
                    if (!finite(y)) {
                        nonpositive++;
                        pen = false;
                        last = null;
                        return;
                    }
                    const p = this.map(point.x, y);
                    d += (pen ? 'L' : 'M') + p[0] + ',' + p[1];
                    pen = true;
                    last = p;
                    drawn++;
                });
                svgElement('path', {
                    d,
                    fill: 'none',
                    stroke: colors[index % colors.length],
                    'stroke-width': 1.8,
                    'stroke-dasharray': series.reference ? '7 5' : 'none',
                    'data-series': index
                }, group);
                if (last) {
                    svgElement('circle', {
                        cx: last[0],
                        cy: last[1],
                        r: 3,
                        fill: colors[index % colors.length]
                    }, group);
                }
            });
            if (!drawn) {
                svgElement('text', {
                    ...textStyle,
                    x: b.left + b.width / 2,
                    y: 185,
                    'text-anchor': 'middle'
                }, this.svg, '当前选择没有可绘制的有限值');
            }
            this.selection = svgElement('rect', {
                width: 0,
                height: 0,
                fill: '#1377bd22',
                stroke: '#1377bd',
                'pointer-events': 'none'
            }, this.svg);
            this.note.textContent = '当前可见曲线 ' + (this.data.series.length - this.hidden.size) + ' 条 · 记录 ' + count + ' 条 · 无效 / 不可用 ' + invalid + ' 条 · 对数轴不显示的非正值 ' + nonpositive + ' 条。曲线末点以圆点标记（末条无效则不标记）。';
        }

        download() {
            const clone = this.svg.cloneNode(true);
            clone.setAttribute('xmlns', NS);
            clone.setAttribute('width', '1040');
            clone.setAttribute('height', '414');
            svgElement('title', {}, clone, this.data.title);
            svgElement('desc', {}, clone, this.yLabel() + '; ' + this.data.series.filter((_, i) => !this.hidden.has(i)).map(s => s.label + ' [' + s.job_id + ']').join('; '));
            const blob = new Blob([new XMLSerializer().serializeToString(clone)], {
                type: 'image/svg+xml;charset=utf-8'
            });
            const url = URL.createObjectURL(blob),
                link = element('a', null, document.body, {
                    href: url,
                    download: this.data.id + '-view.svg'
                });
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        }
    }
    charts.forEach(data => new Chart(data));
    if (!charts.length) {
        element('p', '所选作业没有可绘制的监控或场比较记录，请查看作业状态和诊断。', document.getElementById('chart-list'));
    }
    document.getElementById('table-filter').addEventListener('input', event => {
        const text = event.target.value.trim().toLowerCase();
        document.querySelectorAll('.filterable tbody tr').forEach(row => {
            row.hidden = !row.textContent.toLowerCase().includes(text);
        });
    });
})();
