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
        constructor(chart) {
            this.chart = chart;
            this.log = chart.yscale === 'log';
            this.statistic = 'max';
            this.hidden = new Set();
            this.card = element('article', null, document.getElementById('chart-list'), {
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
            if (chart.kind === 'field') {
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
            if (this.chart.kind === 'field') {
                const key = this.chart.error_kind + '.' + this.statistic;
                return point.metrics ? point.metrics[key] : null;
            }
            return point.y;
        }

        yLabel() {
            if (this.chart.kind !== 'field') {
                return this.chart.ylabel;
            }
            const statistic = statistics.find(item => item[0] === this.statistic)[1];
            if (this.chart.error_kind === 'normalized_error') {
                return statistic + ' · 归一化误差 [%]';
            }
            return statistic + ' · 绝对误差 [' + (this.chart.unit || '无量纲') + ']';
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
                + ' 条 · 完整记录 ' + count + ' 条 · 无效 / 不可用 ' + invalid
                + ' 条 · 对数轴非正值 ' + nonpositive
                + ' 条。无效及对数轴非正值保留为断点，切换线性轴可查看零值和负值；原始记录保留在数据明细中。';
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

    window.simtestCharts = charts.map(chart => new Chart(chart));
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
