(() => {
    'use strict';

    const charts = JSON.parse(document.getElementById('chart-data').textContent);
    const colors = ['#1377bd', '#d66c16', '#239278', '#a254b5', '#c1425a', '#668329', '#675fc1', '#087f91'];
    const finite = value => typeof value === 'number' && Number.isFinite(value);
    const statistics = [['max', '最大值'], ['mean', '体积加权平均值'], ['rms', '体积加权 RMS']];

    function element(tag, text, parent, attributes = {}) {
        const node = document.createElement(tag);
        if (text != null) {
            node.textContent = text;
        }
        Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
        if (parent) {
            parent.append(node);
        }
        return node;
    }

    function format(value) {
        if (!finite(value)) {
            return '不可用';
        }
        return Number(value.toPrecision(6)).toString();
    }

    class Chart {
        constructor(chart, container) {
            this.chart = chart;
            this.log = chart.yscale === 'log';
            this.statistic = 'max';
            this.hidden = new Set();
            this.card = element('article', null, container, {
                class: 'chart', id: chart.id
            });
            element('h3', chart.title, this.card);
            element('p', chart.description, this.card, {class: 'chart-subtitle'});
            const bar = element('div', null, this.card, {
                class: 'toolbar', role: 'group', 'aria-label': '图表操作'
            });
            this.button(bar, '放大 +', 'zoom-in', () => this.zoom(0.7));
            this.button(bar, '缩小 −', 'zoom-out', () => this.zoom(1 / 0.7));
            this.button(bar, '重置', 'reset', () => this.reset());
            this.selectButton = this.button(bar, '框选', 'select', () => this.mode(true));
            this.panButton = this.button(bar, '平移', 'pan', () => this.mode(false));
            this.button(bar, '末段放大', 'tail', () => this.instance.dispatchAction({
                type: 'dataZoom', dataZoomIndex: 0, start: 80, end: 100
            }));
            const label = element('label', 'Y 轴', bar);
            const scale = element('select', null, label, {'aria-label': 'Y 轴刻度'});
            element('option', '线性', scale, {value: 'linear'});
            element('option', '对数 log₁₀', scale, {value: 'log'});
            scale.value = chart.yscale || 'linear';
            scale.onchange = () => {
                this.log = scale.value === 'log';
                this.render();
            };
            if (chart.kind === 'analytical') {
                const metric = element('select', null, bar, {'aria-label': '误差统计量'});
                statistics.forEach(([key, name]) => element('option', name, metric, {value: key}));
                metric.onchange = () => {
                    this.statistic = metric.value;
                    this.render();
                };
            }
            this.button(bar, '全屏', 'fullscreen', async () => {
                try {
                    if (document.fullscreenElement) {
                        await document.exitFullscreen();
                    } else {
                        await this.card.requestFullscreen();
                    }
                } catch (error) {
                    this.note.textContent = '浏览器未允许全屏，可使用浏览器窗口最大化。';
                }
                this.instance.resize();
            });
            this.button(bar, '导出当前 SVG', 'export', () => this.download());
            this.plot = element('div', null, this.card, {
                class: 'plot', role: 'img', 'aria-label': chart.title
            });
            this.note = element('p', null, this.card, {class: 'chart-note', role: 'status'});
            this.instance = window.echarts.init(this.plot, null, {renderer: 'svg'});
            const legend = element('div', null, this.card, {class: 'legend', 'aria-label': '曲线显隐'});
            chart.series.forEach((series, index) => {
                const button = this.button(legend, null, 'legend', () => {
                    if (this.hidden.has(index)) {
                        this.hidden.delete(index);
                    } else {
                        this.hidden.add(index);
                    }
                    button.setAttribute('aria-pressed', String(!this.hidden.has(index)));
                    this.instance.dispatchAction({type: 'legendToggleSelect', name: this.name(index)});
                    this.updateNote();
                });
                button.setAttribute('aria-pressed', 'true');
                button.title = series.job_id || '';
                const swatch = element('span', null, button, {class: 'swatch'});
                swatch.style.background = colors[index % colors.length];
                element('span', series.label, button);
            });
            this.render();
            this.plot.addEventListener('dblclick', () => this.reset());
            this.resizeObserver = new ResizeObserver(() => this.instance.resize());
            this.resizeObserver.observe(this.plot);
        }

        button(parent, text, action, callback) {
            const button = element('button', text, parent, {type: 'button', 'data-action': action});
            button.onclick = callback;
            return button;
        }

        name(index) {
            return String(index) + ': ' + this.chart.series[index].label;
        }

        value(point) {
            if (this.chart.kind === 'analytical') {
                const key = this.chart.error_kind + '.' + this.statistic;
                return point.metrics ? point.metrics[key] : null;
            }
            return point.y;
        }

        yLabel() {
            if (this.chart.kind !== 'analytical') {
                return this.chart.ylabel;
            }
            const statistic = statistics.find(item => item[0] === this.statistic)[1];
            return statistic + ' · 归一化误差 [%]';
        }

        tooltip(params) {
            const box = element('div', null, null, {class: 'chart-tooltip'});
            for (const item of params) {
                const series = this.chart.series[item.seriesIndex];
                const point = series.points[item.dataIndex];
                if (!point) {
                    continue;
                }
                element('strong', series.label, box);
                element('div', '作业：' + (series.job_id || '参考值'), box);
                element('div', this.chart.xlabel + '：' + point.x, box);
                element('div', this.yLabel() + '：' + String(this.value(point)), box);
                if (point.step != null) {
                    element('div', '步序号：' + point.step, box);
                }
                if (point.time != null) {
                    element('div', '物理时间 [s]：' + point.time, box);
                }
                if (point.quality) {
                    element('div', '数据质量：' + point.quality, box);
                }
            }
            return box;
        }

        render() {
            const selected = {};
            let positiveMin = Infinity;
            let positiveMax = -Infinity;
            let dataMin = Infinity;
            let dataMax = -Infinity;
            const series = this.chart.series.map((source, index) => {
                selected[this.name(index)] = !this.hidden.has(index);
                const data = source.points.map(point => {
                    const value = this.value(point);
                    let plotted = value;
                    if (!finite(point.x) || !finite(value) || (this.log && value <= 0)) {
                        plotted = null;
                    } else if (value > 0) {
                        positiveMin = Math.min(positiveMin, value);
                        positiveMax = Math.max(positiveMax, value);
                    }
                    if (finite(plotted)) {
                        dataMin = Math.min(dataMin, plotted);
                        dataMax = Math.max(dataMax, plotted);
                    }
                    return [point.x, plotted];
                });
                return {
                    name: this.name(index), type: 'line', data, connectNulls: false,
                    smooth: false, showSymbol: true, symbol: 'circle', symbolSize: 3,
                    sampling: 'none', animation: false,
                    lineStyle: {width: 1.6, type: source.reference ? 'dashed' : 'solid'},
                    emphasis: {focus: 'series'}
                };
            });
            const yAxis = {
                type: this.log ? 'log' : 'value', logBase: 10, name: this.yLabel(),
                nameLocation: 'middle', nameGap: 66, scale: true,
                axisLabel: {formatter: format}, splitLine: {lineStyle: {color: '#e2e9ef'}}
            };
            if (this.log) {
                if (positiveMin === Infinity) {
                    yAxis.min = 0.1;
                    yAxis.max = 1;
                } else {
                    yAxis.min = 10 ** (Math.floor(Math.log10(positiveMin)) - 0.05);
                    yAxis.max = 10 ** (Math.ceil(Math.log10(positiveMax)) + 0.05);
                }
            } else if (dataMin !== Infinity) {
                const span = dataMax - dataMin;
                const pad = span > 0 ? span * 0.05 : (Math.abs(dataMax) * 0.1 || 0.5);
                yAxis.min = dataMin >= 0 ? Math.max(0, dataMin - pad) : dataMin - pad;
                yAxis.max = dataMax + pad;
            }
            this.instance.setOption({
                animation: false, color: colors, backgroundColor: '#fff',
                textStyle: {fontFamily: 'Segoe UI, Microsoft YaHei, sans-serif'},
                grid: {left: 98, right: 30, top: 30, bottom: 104},
                legend: {show: false, selected},
                tooltip: {
                    trigger: 'axis', confine: true, renderMode: 'html',
                    formatter: params => this.tooltip(params),
                    axisPointer: {type: 'line'}, extraCssText: 'max-width:90%;white-space:normal;'
                },
                toolbox: {show: false, feature: {dataZoom: {}}},
                xAxis: {
                    type: 'value', name: this.chart.xlabel, nameLocation: 'middle', nameGap: 30,
                    min: 'dataMin', max: 'dataMax', axisLabel: {formatter: format}
                },
                yAxis,
                dataZoom: [
                    {type: 'slider', xAxisIndex: 0, filterMode: 'none', bottom: 18, height: 24, start: 0, end: 100},
                    {
                        type: 'inside', xAxisIndex: 0, filterMode: 'none', start: 0, end: 100,
                        zoomOnMouseWheel: true, moveOnMouseMove: true, moveOnMouseWheel: false
                    },
                    {type: 'inside', yAxisIndex: 0, filterMode: 'none', disabled: true, start: 0, end: 100}
                ],
                series
            }, {notMerge: true});
            this.mode(false);
            this.updateNote();
        }

        updateNote() {
            let count = 0;
            let invalid = 0;
            let nonpositive = 0;
            this.chart.series.forEach((series, index) => {
                if (this.hidden.has(index)) {
                    return;
                }
                for (const point of series.points) {
                    count++;
                    const value = this.value(point);
                    if (!finite(point.x) || !finite(value)) {
                        invalid++;
                    } else if (this.log && value <= 0) {
                        nonpositive++;
                    }
                }
            });
            this.note.textContent = '可见曲线 ' + (this.chart.series.length - this.hidden.size)
                + ' 条 · 曲线采样 ' + count + ' 条 · 无效 / 不可用 ' + invalid
                + ' 条 · 对数轴非正值 ' + nonpositive
                + ' 条。无效及对数轴非正值保留为断点，切换线性轴可查看零值和负值；'
                + '原始记录保留在作业归档中。';
        }

        mode(selecting) {
            this.instance.dispatchAction({type: 'takeGlobalCursor', key: 'dataZoomSelect', dataZoomSelectActive: selecting});
            this.selectButton.setAttribute('aria-pressed', String(selecting));
            this.panButton.setAttribute('aria-pressed', String(!selecting));
        }

        zoom(factor) {
            const current = this.instance.getOption().dataZoom[0];
            const center = (current.start + current.end) / 2;
            const half = (current.end - current.start) * factor / 2;
            this.instance.dispatchAction({
                type: 'dataZoom', dataZoomIndex: 0,
                start: Math.max(0, center - half), end: Math.min(100, center + half)
            });
        }

        reset() {
            this.instance.dispatchAction({
                type: 'dataZoom', batch: [{dataZoomIndex: 0, start: 0, end: 100}, {dataZoomIndex: 2, start: 0, end: 100}]
            });
            this.mode(false);
        }

        download() {
            const svg = this.plot.querySelector('svg').cloneNode(true);
            svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
            const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
            title.textContent = this.chart.title + ' — ' + this.yLabel();
            svg.prepend(title);
            const description = document.createElementNS('http://www.w3.org/2000/svg', 'desc');
            description.textContent = this.chart.series.filter((_, index) => !this.hidden.has(index))
                .map(series => series.label + ' [' + series.job_id + ']').join('; ');
            svg.prepend(description);
            const blob = new Blob([new XMLSerializer().serializeToString(svg)], {type: 'image/svg+xml;charset=utf-8'});
            const url = URL.createObjectURL(blob);
            const link = element('a', null, document.body, {href: url, download: this.chart.id + '-view.svg'});
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        }
    }

    class DataTable {
        constructor(table, host) {
            this.table = table;
            this.host = host;
            this.columns = Array.from(table.tHead.rows[0].cells).map(cell => ({
                key: cell.dataset.key, label: cell.textContent, type: cell.dataset.type
            })).filter(column => column.key !== '_index');
            this.body = table.tBodies[0];
            this.rows = Array.from(this.body.rows);
            this.build();
        }
        build() {
            const box = element('div', null, this.host, {class: 'filter'});
            const toggle = element('button', null, box, {type: 'button', class: 'filter-toggle', title: '筛选 / 排序'});
            toggle.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path fill="currentColor" d="M3 5h18l-7 8v6l-4 2v-8L3 5z"/></svg>';
            const panel = element('div', null, box, {class: 'filter-panel'});
            panel.hidden = true;
            toggle.onclick = () => {
                panel.hidden = !panel.hidden;
                const open = !panel.hidden;
                box.classList.toggle('is-open', open);
                const panelHead = box.closest('.panel-head');
                if (panelHead) {
                    panelHead.classList.toggle('filter-open', open);
                }
            };
            const head = element('div', null, panel, {class: 'filter-head'});
            element('strong', '设置筛选条件', head);
            const modeBox = element('div', null, head, {class: 'filter-mode'});
            element('span', '符合以下', modeBox);
            const mode = element('select', null, modeBox);
            element('option', '所有', mode, {value: 'all'});
            element('option', '任一', mode, {value: 'any'});
            const list = element('div', null, panel, {class: 'filter-list'});
            const add = element('button', '+ 添加条件', panel, {type: 'button', class: 'filter-add'});
            const actions = element('div', null, panel, {class: 'filter-actions'});
            element('button', '应用', actions, {type: 'button', class: 'primary'}).onclick = () => this.apply(mode.value, list);
            element('button', '重置', actions, {type: 'button'}).onclick = () => {
                list.replaceChildren();
                this.row(list);
                this.apply('all', list);
            };
            add.onclick = () => this.row(list);
            this.row(list);
            this.apply('all', list);
        }
        row(list) {
            const row = element('div', null, list, {class: 'filter-row'});
            const field = element('select', null, row);
            this.columns.forEach(column => element('option', column.label, field, {value: column.key}));
            const operator = element('select', null, row);
            const input = element('input', null, row);
            const order = element('select', null, row, {class: 'filter-order', title: '排序'});
            element('option', '不排序', order, {value: ''});
            element('option', '升序', order, {value: 'asc'});
            element('option', '降序', order, {value: 'desc'});
            order.onchange = () => {
                if (!order.value) {
                    return;
                }
                list.querySelectorAll('.filter-order').forEach(other => {
                    if (other !== order) {
                        other.value = '';
                    }
                });
            };
            const update = () => {
                operator.replaceChildren();
                const type = this.columns.find(column => column.key === field.value).type;
                const operators = type === 'number'
                    ? [['eq', '='], ['ne', '≠'], ['gt', '>'], ['ge', '≥'], ['lt', '<'], ['le', '≤']]
                    : [['eq', '等于'], ['ne', '不等于'], ['contains', '包含']];
                operators.forEach(([key, label]) => element('option', label, operator, {value: key}));
                input.type = type === 'number' ? 'number' : 'text';
                input.placeholder = '值';
            };
            field.onchange = update;
            update();
            element('button', '×', row, {type: 'button', class: 'filter-remove'}).onclick = () => row.remove();
        }
        apply(mode, list) {
            const conditions = Array.from(list.children).map(row => {
                const selects = row.querySelectorAll('select');
                return {
                    key: selects[0].value,
                    op: selects[1].value,
                    value: row.querySelector('input').value,
                    order: selects[2].value,
                    type: this.columns.find(column => column.key === selects[0].value).type
                };
            });
            const filters = conditions.filter(item => item.value !== '');
            const sorted = conditions.find(item => item.order);
            const test = (data, item) => {
                const actual = data[item.key];
                if (actual == null) {
                    return false;
                }
                if (item.op === 'contains') {
                    return String(actual).includes(item.value);
                }
                if (item.type === 'number') {
                    const left = Number(actual);
                    const right = Number(item.value);
                    if (item.op === 'eq') return left === right;
                    if (item.op === 'ne') return left !== right;
                    if (item.op === 'gt') return left > right;
                    if (item.op === 'ge') return left >= right;
                    if (item.op === 'lt') return left < right;
                    return left <= right;
                }
                if (item.op === 'eq') return String(actual) === item.value;
                if (item.op === 'ne') return String(actual) !== item.value;
                return String(actual).includes(item.value);
            };
            const visible = this.rows.filter(row => {
                const data = JSON.parse(row.dataset.values);
                if (!filters.length) {
                    return true;
                }
                const results = filters.map(item => test(data, item));
                return mode === 'any' ? results.some(Boolean) : results.every(Boolean);
            });
            if (sorted) {
                const column = this.columns.find(item => item.key === sorted.key);
                visible.sort((a, b) => {
                    const left = JSON.parse(a.dataset.values)[sorted.key];
                    const right = JSON.parse(b.dataset.values)[sorted.key];
                    const value = column.type === 'number'
                        ? Number(left) - Number(right)
                        : String(left).localeCompare(String(right));
                    return sorted.order === 'desc' ? -value : value;
                });
            }
            this.body.replaceChildren(...visible);
            visible.forEach((row, index) => { row.cells[0].textContent = String(index + 1); });
        }
    }

    document.querySelectorAll('[data-table-id]').forEach(wrapper => {
        const table = wrapper.querySelector('table');
        const host = document.querySelector('[data-filter-for="' + wrapper.dataset.tableId + '"]');
        if (host && table) {
            new DataTable(table, host);
        }
    });

    const sections = Array.from(document.querySelectorAll('[data-section]'));
    sections.forEach(section => {
        const toggle = section.querySelector('.section-toggle');
        const set = collapsed => {
            section.classList.toggle('collapsed', collapsed);
            toggle.setAttribute('aria-expanded', String(!collapsed));
        };
        toggle.onclick = () => set(!section.classList.contains('collapsed'));
        section.querySelector('h2').onclick = () => set(!section.classList.contains('collapsed'));
    });
    const floating = document.getElementById('floating-collapse');
    const syncFloating = () => {
        const collapsed = sections.every(section => section.classList.contains('collapsed'));
        floating.dataset.collapsed = String(collapsed);
        floating.textContent = collapsed ? '全部展开' : '全部收起';
    };
    const setAll = collapsed => {
        sections.forEach(section => section.classList.toggle('collapsed', collapsed));
        syncFloating();
    };
    document.getElementById('expand-all').onclick = () => setAll(false);
    document.getElementById('collapse-all').onclick = () => setAll(true);
    floating.onclick = () => setAll(floating.dataset.collapsed !== 'true');
    sections.forEach(section => {
        const toggle = section.querySelector('.section-toggle');
        const original = toggle.onclick;
        toggle.onclick = () => { original(); syncFloating(); };
        const heading = section.querySelector('h2');
        const click = heading.onclick;
        heading.onclick = () => { click(); syncFloating(); };
    });
    syncFloating();

    const groups = {residual: 'residual-charts', analytical: 'analytical-charts', monitor: 'monitor-charts'};
    const flat = [];
    Object.keys(groups).forEach(kind => {
        const container = document.getElementById(groups[kind]);
        charts.filter(chart => chart.kind === kind).forEach(chart => {
            flat.push(new Chart(chart, container));
        });
        if (!container.children.length) {
            container.closest('section').classList.add('empty');
        }
    });
    window.simtestCharts = flat;
})();
