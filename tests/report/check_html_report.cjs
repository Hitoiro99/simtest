/* Optional offline browser regression: Node 22+ and installed Edge/Chromium. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const {
    spawn
} = require('node:child_process');
const {
    pathToFileURL
} = require('node:url');

async function main() {
    const report = path.resolve(process.argv[2] || '');
    if (!report.endsWith('.html')) {
        throw Error('Pass the generated report.html path');
    }
    const executable = process.argv[3] || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
    const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'simtest-browser-'));
    const browser = spawn(executable, ['--headless=new', '--no-first-run', '--no-default-browser-check',
        '--disable-background-networking', '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank'
    ], {
        windowsHide: true,
        stdio: 'ignore'
    });
    let socket;
    try {
        let port;
        for (let attempt = 0; attempt < 100; attempt++) {
            try {
                port = (await fs.readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0];
                break;
            } catch {
                await new Promise(resolve => setTimeout(resolve, 100));
            }
        }
        assert.ok(port, 'Browser did not start');
        const tabs = await (await fetch('http://127.0.0.1:' + port + '/json/list')).json();
        socket = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
        await new Promise((resolve, reject) => {
            socket.onopen = resolve;
            socket.onerror = reject;
        });
        let sequence = 0;
        const pending = new Map();
        const errors = [];
        const networkRequests = [];
        socket.onmessage = event => {
            const message = JSON.parse(event.data);
            if (message.method === 'Network.requestWillBeSent' && /^https?:/.test(message.params.request.url)) {
                networkRequests.push(message.params.request.url);
            }
            if (message.method === 'Runtime.exceptionThrown') {
                errors.push(message.params.exceptionDetails);
            }
            if (message.id && pending.has(message.id)) {
                const {
                    resolve,
                    reject,
                    timer
                } = pending.get(message.id);
                clearTimeout(timer);
                pending.delete(message.id);
                if (message.error) {
                    reject(Error(JSON.stringify(message.error)));
                } else {
                    resolve(message.result);
                }
            }
        };
        const call = (method, params = {}) => new Promise((resolve, reject) => {
            const id = ++sequence;
            const timer = setTimeout(() => {
                pending.delete(id);
                reject(Error('Timed out: ' + method));
            }, 10000);
            pending.set(id, {
                resolve,
                reject,
                timer
            });
            socket.send(JSON.stringify({
                id,
                method,
                params
            }));
        });
        const evaluate = async expression => {
            const value = await call('Runtime.evaluate', {
                expression,
                returnByValue: true,
                awaitPromise: true
            });
            if (value.exceptionDetails) {
                throw Error(JSON.stringify(value.exceptionDetails));
            }
            return value.result.value;
        };
        await call('Runtime.enable');
        await call('Page.enable');
        await call('Network.enable');
        await call('Network.emulateNetworkConditions', {
            offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0
        });
        await call('Emulation.setDeviceMetricsOverride', {
            width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false
        });
        await call('Page.navigate', {url: pathToFileURL(report).href});
        const settle = () => new Promise(resolve => setTimeout(resolve, 150));
        for (let attempt = 0; attempt < 100; attempt++) {
            if (await evaluate('window.simtestCharts && window.simtestCharts.length > 0')) {
                break;
            }
            await settle();
        }
        const charts = await evaluate('JSON.parse(document.getElementById("chart-data").textContent)');
        assert.ok(charts.length > 0, 'No charts generated');
        assert.equal(await evaluate('window.simtestCharts.length'), charts.length);
        assert.equal(await evaluate('document.querySelectorAll(".chart").length'), charts.length);
        assert.equal(await evaluate('echarts.version'), '5.6.0');
        assert.ok(charts.every(chart => chart.group && chart.group.id && chart.renderer),
            'Every chart must declare its renderer and report group');
        assert.ok(charts.every(chart => Array.isArray(chart.path) && chart.path.length > 0),
            'Every chart must declare a non-empty structured path');
        assert.ok(charts.every(chart => /Step/.test(chart.xlabel)), 'Every chart must use the step axis');
        const fieldCharts = charts.filter(chart => chart.kind === 'analytical');
        assert.ok(fieldCharts.length > 0, 'Use a report containing field comparisons');
        assert.equal(charts.filter(chart => chart.kind === 'monitor').length, 0,
            'An analytical-only case must not show an experimental-monitor section');
        assert.equal(await evaluate('document.querySelectorAll("[data-chart-group]").length'),
            new Set(charts.map(chart => chart.group.id)).size);
        const hierarchy = await evaluate(`(() => {
            const charts = JSON.parse(document.getElementById('chart-data').textContent);
            const prefixes = new Set();
            charts.forEach(chart => chart.path.forEach((part, index) => {
                prefixes.add(chart.group.id + ':' + JSON.stringify(chart.path.slice(0, index + 1)));
            }));
            const nodes = Array.from(document.querySelectorAll('[data-chart-group] .chart-tree-node'));
            const actual = new Set(nodes.map(node => node.closest('[data-chart-group]').dataset.chartGroup
                + ':' + node.dataset.chartPath));
            const sectionTitles = Array.from(document.querySelectorAll('[data-chart-section]')).map(section => ({
                id: section.dataset.chartSection,
                title: section.querySelector('h2').textContent
            }));
            return {
                expected: prefixes.size,
                actual: actual.size,
                uniqueNodes: actual.size === nodes.length,
                sectionTitles
            };
        })()`);
        assert.equal(hierarchy.actual, hierarchy.expected, 'Every unique path prefix needs exactly one node');
        assert.equal(hierarchy.uniqueNodes, true, 'Shared path prefixes must reuse one node');
        const expectedSections = Array.from(new Map(charts.map(chart => [chart.group.id, {
            id: chart.group.id, title: chart.group.title, order: chart.group.order || 100
        }])).values()).sort((left, right) => left.order - right.order || left.id.localeCompare(right.id))
            .map(({id, title}) => ({id, title}));
        assert.deepEqual(hierarchy.sectionTitles, expectedSections,
            'Rendered section titles must come from actual chart group metadata');
        for (const chart of fieldCharts) {
            assert.ok(chart.component, 'Each field chart must identify one component');
            assert.equal(chart.error_kind, 'normalized_error');
            for (const series of chart.series) {
                for (const point of series.points) {
                    assert.ok(Object.keys(point.metrics).every(key => key.startsWith(chart.error_kind + '.')),
                        'Only normalized error metrics may be displayed');
                }
            }
        }
        for (const component of ['x', 'y', 'z', 'magnitude']) {
            assert.ok(fieldCharts.some(
                chart => chart.component === component && chart.error_kind === 'normalized_error'
            ));
        }
        assert.equal(await evaluate('document.body.textContent.includes("完整数值")'), false);
        assert.equal(await evaluate('document.body.textContent.includes("absolute_error")'), false);
        const residualIndex = charts.findIndex(chart => chart.title.includes('residual_p'));
        assert.ok(residualIndex >= 0, 'Missing pressure residual');
        const residual = charts[residualIndex];
        const state = 'window.simtestCharts[' + residualIndex + ']';
        const card = state + '.card';
        const option = () => evaluate(state + '.instance.getOption()');
        const initial = await option();
        assert.equal(initial.xAxis[0].type, 'value');
        assert.match(initial.xAxis[0].name, /Step|步/);
        assert.equal(initial.yAxis[0].type, 'log');
        assert.ok(initial.yAxis[0].splitNumber >= 2 && initial.yAxis[0].splitNumber <= 9);
        assert.equal(initial.yAxis[0].minorTick.show, true);
        assert.ok(await evaluate(
            state + '.instance.getModel().getComponent("yAxis").axis.scale.getTicks().length > 2'
        ), 'Adaptive log axis must render intermediate major ticks');
        for (const series of residual.series.filter(item => !item.reference)) {
            assert.equal(series.points.length, 200, 'Regression sample must retain all 200 steps');
            assert.equal(series.points[0].x, 1);
            assert.equal(series.points[199].x, 200);
            assert.ok(series.points.every(point => point.x === point.step));
            assert.ok(series.points.every(point => point.y === null || point.y === point.raw),
                'Log plotting must not transform original residual values');
        }
        const click = async action => {
            await evaluate(card + '.querySelector("[data-action=' + action + ']").click()');
            await settle();
        };
        const view = async () => {
            const current = await option();
            return [current.dataZoom[0].start, current.dataZoom[0].end];
        };
        const original = await view();
        await click('zoom-in');
        const zoomed = await view();
        assert.ok(zoomed[1] - zoomed[0] < original[1] - original[0]);
        await click('zoom-out');
        await click('reset');
        assert.deepEqual(await view(), original);
        await evaluate(state + '.instance.getDom().scrollIntoView({block:"center"})');
        await settle();
        await click('select');
        assert.equal(await evaluate(card + '.querySelector("[data-action=select]").getAttribute("aria-pressed")'),
            'true', 'Box zoom mode did not activate');
        await click('reset');
        assert.equal(await evaluate('document.querySelectorAll(".filter-toggle").length'),
            await evaluate('document.querySelectorAll("[data-table-id]").length'),
            'Each actually rendered table needs one filter');
        assert.equal(await evaluate('document.querySelectorAll(".filter-order").length'), 0,
            'Sorting must not remain in the filter panel');
        assert.equal(await evaluate('document.querySelectorAll("th[data-key=job_id] .sort-button").length'), 0,
            'Job IDs must not expose meaningless sorting controls');
        assert.ok(await evaluate('document.querySelectorAll("th[data-sortable=true] .sort-button").length > 0'));
        assert.equal(await evaluate('document.querySelector("#jobs tbody tr td").textContent'), '1');
        const sorting = await evaluate(`(() => {
            const wrapper = document.createElement('div');
            wrapper.innerHTML = '<table><thead><tr>'
                + '<th data-key="_index" data-type="index" data-sort-type="index" data-sortable="false">序号</th>'
                + '<th data-key="group" data-type="text" data-sort-type="text" data-sortable="true">分组</th>'
                + '<th data-key="value" data-type="number" data-sort-type="number" data-sortable="true">值</th>'
                + '<th data-key="unique" data-type="number" data-sort-type="number" data-sortable="true">唯一值</th>'
                + '<th data-key="job_id" data-type="text" data-sort-type="text" data-sortable="false">作业 ID</th>'
                + '</tr></thead><tbody></tbody></table>';
            const values = [
                {group: 'A', value: 2, unique: 4, job_id: 'd'},
                {group: 'B', value: 2, unique: 2, job_id: 'b'},
                {group: 'A', value: 1, unique: 3, job_id: 'c'},
                {group: 'B', value: 1, unique: 1, job_id: 'a'}
            ];
            const body = wrapper.querySelector('tbody');
            values.forEach(value => {
                const row = document.createElement('tr');
                row.dataset.values = JSON.stringify(value);
                row.innerHTML = '<td></td><td>' + value.group + '</td><td>' + value.value
                    + '</td><td>' + value.unique + '</td><td>' + value.job_id + '</td>';
                body.append(row);
            });
            const host = document.createElement('div');
            const table = new window.simtestDataTable(wrapper.querySelector('table'), host);
            const click = (key, direction) => wrapper.querySelector(
                '[data-sort-key="' + key + '"][data-sort-direction="' + direction + '"]'
            ).click();
            const order = () => Array.from(body.rows).map(row => JSON.parse(row.dataset.values).job_id).join('');
            click('group', 'asc');
            click('value', 'asc');
            const multi = order();
            const priorities = table.sorts.map(sort => sort.key + ':' + sort.direction).join(',');
            click('value', 'desc');
            const switched = order();
            const switchedPriorities = table.sorts.map(sort => sort.key + ':' + sort.direction).join(',');
            click('value', 'desc');
            const cancelled = table.sorts.map(sort => sort.key).join(',');
            click('group', 'asc');
            click('unique', 'asc');
            const disabled = Array.from(wrapper.querySelectorAll('.sort-button')).filter(button => button.disabled).length;
            return {multi, priorities, switched, switchedPriorities, cancelled, disabled};
        })()`);
        assert.deepEqual(sorting, {
            multi: 'cdab', priorities: 'group:asc,value:asc', switched: 'dcba',
            switchedPriorities: 'group:asc,value:desc', cancelled: 'group', disabled: 4
        });
        await evaluate('document.querySelector("#jobs h2").click()');
        assert.equal(await evaluate('document.querySelector("#jobs").classList.contains("collapsed")'), true);
        await evaluate('document.getElementById("expand-all").click()');
        assert.equal(await evaluate('document.querySelector("#jobs").classList.contains("collapsed")'), false);
        const branchState = await evaluate(`(() => {
            const group = document.querySelector('[data-chart-group="analytical"]');
            const siblings = Array.from(group.children).filter(node => node.classList.contains('chart-tree-node'));
            const first = siblings[0];
            const sibling = siblings[1] || null;
            const button = first.querySelector(':scope > .chart-tree-head .chart-tree-toggle');
            button.click();
            const collapsed = first.classList.contains('collapsed') && button.getAttribute('aria-expanded') === 'false';
            const siblingOpen = !sibling || !sibling.classList.contains('collapsed');
            button.click();
            return {collapsed, siblingOpen, reopened: !first.classList.contains('collapsed')};
        })()`);
        assert.deepEqual(branchState, {collapsed: true, siblingOpen: true, reopened: true},
            'Each hierarchy node must collapse independently without changing siblings');
        await evaluate('document.getElementById("floating-collapse").click()');
        assert.equal(await evaluate('document.querySelectorAll("[data-section].collapsed, .chart-tree-node.collapsed").length'),
            await evaluate('document.querySelectorAll("[data-section], .chart-tree-node").length'));
        assert.equal(await evaluate('document.getElementById("floating-collapse").textContent'), '全部展开');
        await evaluate('document.getElementById("floating-collapse").click()');
        assert.equal(await evaluate('document.querySelectorAll("[data-section].collapsed, .chart-tree-node.collapsed").length'), 0);
        await settle();
        await evaluate('document.querySelector("#jobs .filter-toggle").click()');
        assert.equal(await evaluate('document.querySelector("#jobs .panel-head").classList.contains("filter-open")'), true);
        assert.equal(await evaluate('getComputedStyle(document.querySelector("#jobs .panel-head")).zIndex'), '80');
        assert.equal(await evaluate('getComputedStyle(document.querySelector("#jobs .filter-panel")).zIndex'), '90');
        await evaluate('document.querySelector("#jobs .filter-toggle").click()');
        assert.equal(await evaluate('document.querySelector("#jobs .panel-head").classList.contains("filter-open")'), false);
        await evaluate(state + '.instance.getDom().scrollIntoView({block:"center"})');
        await settle();
        await click('pan');
        assert.equal(await evaluate(card + '.querySelector("[data-action=pan]").getAttribute("aria-pressed")'),
            'true', 'Pan mode did not activate');
        await click('reset');
        const wheelPoint = await evaluate('(()=>{const r=' + state
            + '.instance.getDom().getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height*0.4}})()');
        await call('Input.dispatchMouseEvent', {type: 'mouseWheel', ...wheelPoint, deltaX: 0, deltaY: -100});
        await settle();
        const wheeled = await view();
        assert.ok(wheeled[1] - wheeled[0] < original[1] - original[0]);
        await click('reset');
        await click('tail');
        assert.ok((await view())[0] > original[0], 'Tail view must retain later samples');
        await click('reset');
        await evaluate(card + '.querySelector(".legend button").click()');
        assert.equal(await evaluate(card + '.querySelector(".legend button").getAttribute("aria-pressed")'), 'false');
        await evaluate(card + '.querySelector(".legend button").click()');
        for (const scale of ['linear', 'log']) {
            await evaluate('(()=>{const s=' + card + '.querySelector('
                + JSON.stringify('select[aria-label="Y 轴刻度"]') + ');s.value=' + JSON.stringify(scale)
                + ';s.dispatchEvent(new Event("change"))})()');
            assert.equal((await option()).yAxis[0].type, scale === 'linear' ? 'value' : 'log');
        }
        const hoverIndex = residual.series[0].points.length - 1;
        const hoverStep = residual.series[0].points[hoverIndex].step;
        await evaluate(state + '.instance.dispatchAction({type:"showTip",seriesIndex:0,dataIndex:' + hoverIndex + '})');
        await settle();
        assert.ok(await evaluate(card + '.textContent.includes(' + JSON.stringify('步序号：' + hoverStep) + ')'),
            'Hover must show the original archived step');
        const fieldIndex = charts.findIndex(chart => chart.kind === 'analytical');
        const fieldState = 'window.simtestCharts[' + fieldIndex + ']';
        const metricOptions = await evaluate(
            'Array.from(' + fieldState + '.card.querySelector("select[aria-label=误差统计量]").options).map(o=>o.value)'
        );
        assert.deepEqual(metricOptions, [
            'normalized_error.max', 'normalized_error.mean', 'normalized_error.rms'
        ]);
        const rms = charts[fieldIndex].error_kind + '.rms';
        assert.ok(metricOptions.includes(rms));
        await evaluate(
            '(()=>{const s=' + fieldState + '.card.querySelector("select[aria-label=误差统计量]");s.value='
            + JSON.stringify(rms) + ';s.dispatchEvent(new Event("change"))})()'
        );
        const plotted = await evaluate(fieldState + '.instance.getOption().series[0].data');
        const expected = charts[fieldIndex].series[0].points.map(point => point.metrics[rms]);
        assert.deepEqual(plotted.map(point => Array.isArray(point) ? point[1] : point.value[1]), expected);
        const preserved = await evaluate(`(() => {
            const state = window.simtestCharts[${fieldIndex}];
            const metric = state.card.querySelector('select[aria-label="误差统计量"]');
            const scale = state.card.querySelector('select[aria-label="Y 轴刻度"]');
            scale.value = 'log';
            scale.dispatchEvent(new Event('change'));
            state.instance.dispatchAction({type: 'dataZoom', dataZoomIndex: 0, start: 20, end: 80});
            const legend = state.card.querySelector('.legend button');
            legend.click();
            const leaf = state.card.closest('.chart-tree-node');
            const parent = leaf.parentElement.closest('.chart-tree-node');
            leaf.querySelector(':scope > .chart-tree-head .chart-tree-toggle').click();
            leaf.querySelector(':scope > .chart-tree-head .chart-tree-toggle').click();
            if (parent) {
                parent.querySelector(':scope > .chart-tree-head .chart-tree-toggle').click();
                parent.querySelector(':scope > .chart-tree-head .chart-tree-toggle').click();
            }
            const zoom = state.instance.getOption().dataZoom[0];
            const rect = state.instance.getDom().getBoundingClientRect();
            return {
                metric: metric.value,
                scale: state.instance.getOption().yAxis[0].type,
                zoom: [zoom.start, zoom.end],
                legend: legend.getAttribute('aria-pressed'),
                expanded: !leaf.classList.contains('collapsed') && (!parent || !parent.classList.contains('collapsed')),
                width: rect.width
            };
        })()`);
        assert.equal(preserved.metric, rms);
        assert.equal(preserved.scale, 'log');
        assert.deepEqual(preserved.zoom, [20, 80]);
        assert.equal(preserved.legend, 'false');
        assert.equal(preserved.expanded, true);
        assert.ok(preserved.width > 0, 'Expanded charts must be resized to a visible width');
        assert.ok(await evaluate('document.querySelectorAll("#final tbody tr").length > 0'));
        assert.equal(await evaluate('document.getElementById("table-filter")'), null);
        await click('fullscreen');
    const fullscreenActive = await evaluate('document.fullscreenElement!==null');
    if (fullscreenActive) {
        await evaluate('document.exitFullscreen()');
    }
    assert.ok(await evaluate(`${card}.querySelector('[data-action="fullscreen"]')!==null`));
        await call('Page.setDownloadBehavior', {behavior: 'allow', downloadPath: profile});
        await click('export');
        const svgName = residual.id + '-view.svg';
        for (let attempt = 0; attempt < 30; attempt++) {
            if ((await fs.readdir(profile)).includes(svgName)) {
                break;
            }
            await settle();
        }
        const svg = await fs.readFile(path.join(profile, svgName), 'utf8');
        assert.ok(svg.includes('<svg'));
        assert.equal(await evaluate('new DOMParser().parseFromString(' + JSON.stringify(svg) + ',"image/svg+xml").querySelector("parsererror")===null'), true);
        await fs.mkdir(path.resolve('.inspection'), {recursive: true});
        await evaluate(card + '.scrollIntoView()');
        const chartScreenshot = await call('Page.captureScreenshot', {format: 'png'});
        await fs.writeFile(path.resolve('.inspection/report-chart.png'), Buffer.from(chartScreenshot.data, 'base64'));
        await evaluate('window.scrollTo(0,0)');
        const screenshot = await call('Page.captureScreenshot', {format: 'png'});
        await fs.writeFile(path.resolve('.inspection/report-desktop.png'), Buffer.from(screenshot.data, 'base64'));
        await call('Emulation.setDeviceMetricsOverride', {
            width: 390, height: 844, deviceScaleFactor: 1, mobile: true
        });
        await settle();
        assert.ok(await evaluate('document.documentElement.scrollWidth <= 390'), 'Mobile page overflows viewport');
        assert.deepEqual(errors, []);
        assert.deepEqual(networkRequests, [], 'Offline report attempted external network requests');
        console.log(JSON.stringify({
            report, charts: charts.length,
            checks: ['offline ECharts', 'data-driven chart groups', 'step axes', 'normalized analytical errors',
                'final-step tables', 'all residual steps', 'step/log defaults',
                'adaptive y-axis ticks', 'header multi-sort', 'shared path hierarchy', 'nested collapse state',
                'button zoom', 'selection/pan modes', 'wheel zoom', 'reset', 'tail view', 'legend', 'axis switch',
                'hover', 'metric selection', 'fullscreen', 'SVG export', 'mobile width'],
            javascriptErrors: errors.length, externalRequests: networkRequests.length
        }));
        await call('Browser.close');
    } finally {
        if (socket) {
            socket.close();
        }
        if (browser.exitCode === null) {
            browser.kill();
        }
        // Only remove the uniquely created temporary browser profile.
        const resolved = path.resolve(profile),
            tempRoot = path.resolve(os.tmpdir()) + path.sep;
        assert.ok(resolved.startsWith(tempRoot) && path.basename(resolved).startsWith('simtest-browser-'));
        await fs.rm(resolved, {
            recursive: true,
            force: true,
            maxRetries: 10,
            retryDelay: 100
        });
    }
}
main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
