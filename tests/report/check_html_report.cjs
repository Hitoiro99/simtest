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
        const fieldCharts = charts.filter(chart => chart.kind === 'field');
        assert.ok(fieldCharts.length > 0, 'Use a report containing field comparisons');
        for (const chart of fieldCharts) {
            assert.ok(chart.component, 'Each field chart must identify one component');
            assert.ok(['absolute_error', 'normalized_error'].includes(chart.error_kind));
            for (const series of chart.series) {
                for (const point of series.points) {
                    assert.ok(Object.keys(point.metrics).every(key => key.startsWith(chart.error_kind + '.')),
                        'Different error types must not share a chart');
                }
            }
        }
        for (const component of ['x', 'y', 'z', 'magnitude']) {
            assert.ok(fieldCharts.some(chart => chart.component === component && chart.error_kind === 'absolute_error'));
            assert.ok(fieldCharts.some(chart => chart.component === component && chart.error_kind === 'normalized_error'));
        }
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
        for (const series of residual.series.filter(item => !item.reference)) {
            assert.equal(series.points.length, 1000, 'Regression sample must retain all 1000 steps');
            assert.equal(series.points[0].x, 1);
            assert.equal(series.points[999].x, 1000);
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
        await evaluate(card + '.scrollIntoView()');
        await settle();
        const rect = await evaluate('(()=>{const r=' + state + '.instance.getDom().getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}})()');
        const at = (x, y) => ({x: rect.x + x * rect.w, y: rect.y + y * rect.h});
        const drag = async (a, b) => {
            await call('Input.dispatchMouseEvent', {type: 'mousePressed', ...at(...a), button: 'left', clickCount: 1});
            for (let step = 1; step <= 6; step++) {
                await call('Input.dispatchMouseEvent', {
                    type: 'mouseMoved', ...at(a[0] + (b[0] - a[0]) * step / 6, a[1] + (b[1] - a[1]) * step / 6),
                    button: 'left', buttons: 1
                });
            }
            await call('Input.dispatchMouseEvent', {type: 'mouseReleased', ...at(...b), button: 'left', clickCount: 1});
            await settle();
        };
        await click('select');
        await drag([0.3, 0.3], [0.7, 0.6]);
        const selected = await view();
        assert.ok(selected[1] - selected[0] < original[1] - original[0], 'Box zoom did not change range');
        await click('pan');
        const beforePan = await view();
        await drag([0.45, 0.4], [0.55, 0.4]);
        assert.notEqual((await view())[0], beforePan[0], 'Pan did not move range');
        await click('reset');
        await call('Input.dispatchMouseEvent', {type: 'mouseWheel', ...at(0.5, 0.4), deltaX: 0, deltaY: -100});
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
            await evaluate('(()=>{const s=' + card + '.querySelector("select[aria-label=\"Y 轴刻度\"]");s.value=' + JSON.stringify(scale) + ';s.dispatchEvent(new Event("change"))})()');
            assert.equal((await option()).yAxis[0].type, scale === 'linear' ? 'value' : 'log');
        }
        await evaluate(state + '.instance.dispatchAction({type:"showTip",seriesIndex:0,dataIndex:999})');
        await settle();
        assert.ok(await evaluate(card + '.textContent.includes("1000")'), 'Hover must show original step');
        const fieldIndex = charts.findIndex(chart => chart.kind === 'field');
        const fieldState = 'window.simtestCharts[' + fieldIndex + ']';
        const metricOptions = await evaluate('Array.from(' + fieldState + '.card.querySelector("select[aria-label=误差统计量]").options).map(o=>o.value)');
        assert.deepEqual(metricOptions, ['max', 'mean', 'rms']);
        const rms = charts[fieldIndex].error_kind + '.rms';
        assert.ok(metricOptions.includes('rms'));
        await evaluate('(()=>{const s=' + fieldState + '.card.querySelector("select[aria-label=误差统计量]");s.value=' + JSON.stringify('rms') + ';s.dispatchEvent(new Event("change"))})()');
        const plotted = await evaluate(fieldState + '.instance.getOption().series[0].data');
        const expected = charts[fieldIndex].series[0].points.map(point => point.metrics[rms]);
        assert.deepEqual(plotted.map(point => Array.isArray(point) ? point[1] : point.value[1]), expected);
        const rowCount = await evaluate('document.querySelectorAll(".filterable tbody tr:not([hidden])").length');
        assert.ok(rowCount > 0);
        await evaluate('(()=>{const f=document.getElementById("table-filter");f.value="not-a-job";f.dispatchEvent(new Event("input"))})()');
        assert.equal(await evaluate('document.querySelectorAll(".filterable tbody tr:not([hidden])").length'), 0);
        await evaluate('(()=>{const f=document.getElementById("table-filter");f.value="";f.dispatchEvent(new Event("input"))})()');
        assert.equal(await evaluate('document.querySelectorAll(".filterable tbody tr:not([hidden])").length'), rowCount);
        await click('fullscreen');
        assert.ok(await evaluate('document.fullscreenElement!==null'));
        await evaluate('document.exitFullscreen()');
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
            checks: ['offline ECharts', 'separate components and errors', 'all residual steps', 'step/log defaults',
                'button zoom', 'box zoom', 'pan', 'wheel zoom', 'reset', 'tail view', 'legend', 'axis switch',
                'hover', 'metric selection', 'table filter', 'fullscreen', 'SVG export', 'mobile width'],
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
