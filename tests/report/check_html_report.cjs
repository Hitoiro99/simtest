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
        socket.onmessage = event => {
            const message = JSON.parse(event.data);
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
        await call('Emulation.setDeviceMetricsOverride', {
            width: 1440,
            height: 1000,
            deviceScaleFactor: 1,
            mobile: false
        });
        await call('Page.navigate', {
            url: pathToFileURL(report).href
        });
        for (let attempt = 0; attempt < 100; attempt++) {
            if (await evaluate('document.querySelectorAll(".chart svg").length > 0')) {
                break;
            }
            await new Promise(resolve => setTimeout(resolve, 50));
        }
        assert.equal(await evaluate('document.querySelectorAll(".chart").length'), 4);
        const view = () => evaluate('JSON.parse(document.querySelector(".chart svg").dataset.view)');
        const click = text => evaluate('Array.from(document.querySelector(".chart .toolbar").querySelectorAll("button")).find(b=>b.textContent===' + JSON.stringify(text) + ').click()');
        const original = await view();
        await click('放大 +');
        const zoomed = await view();
        assert.ok(zoomed[1] - zoomed[0] < original[1] - original[0]);
        await click('缩小 −');
        assert.ok(Math.abs((await view())[0] - original[0]) < 1e-10);
        await click('重置');
        assert.deepEqual(await view(), original);
        await evaluate('document.querySelector(".chart").scrollIntoView()');
        const rect = await evaluate('(()=>{const r=document.querySelector(".chart svg").getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}})()');
        const at = (x, y) => ({
            x: rect.x + x * rect.w / 1040,
            y: rect.y + y * rect.h / 414
        });
        const drag = async (a, b) => {
            await call('Input.dispatchMouseEvent', {
                type: 'mousePressed',
                ...at(...a),
                button: 'left',
                clickCount: 1
            });
            await call('Input.dispatchMouseEvent', {
                type: 'mouseMoved',
                ...at(...b),
                button: 'left',
                buttons: 1
            });
            await call('Input.dispatchMouseEvent', {
                type: 'mouseReleased',
                ...at(...b),
                button: 'left',
                clickCount: 1
            });
        };
        await drag([280, 90], [760, 280]);
        assert.ok((await view())[1] - (await view())[0] < original[1] - original[0]);
        await click('重置');
        await click('平移');
        await drag([400, 180], [480, 200]);
        assert.notEqual((await view())[0], original[0]);
        await click('平移');
        await click('重置');
        await call('Input.dispatchMouseEvent', {
            type: 'mouseWheel',
            ...at(540, 180),
            deltaX: 0,
            deltaY: -100
        });
        await new Promise(resolve => setTimeout(resolve, 100));
        assert.ok((await view())[1] - (await view())[0] < original[1] - original[0]);
        await click('重置');
        await evaluate('document.querySelector(".chart .legend button").click()');
        assert.equal(await evaluate('document.querySelector(".chart .legend button").getAttribute("aria-pressed")'), 'false');
        await evaluate('document.querySelector(".chart .legend button").click()');
        await evaluate('(()=>{const s=document.querySelector(".chart select");s.value="log";s.dispatchEvent(new Event("change"))})()');
        assert.ok(await evaluate('document.querySelector(".chart svg").textContent.includes("(log)")'));
        await evaluate('(()=>{const s=document.querySelector(".chart select");s.value="linear";s.dispatchEvent(new Event("change"))})()');
        const marker = await evaluate('(()=>{const c=document.querySelector(".chart svg circle");return [+c.getAttribute("cx"),+c.getAttribute("cy")]})()');
        await call('Input.dispatchMouseEvent', {
            type: 'mouseMoved',
            ...at(...marker)
        });
        assert.equal(await evaluate('document.querySelector(".chart .tooltip").style.display'), 'block');
        assert.ok(await evaluate('document.querySelector(".chart .tooltip").textContent.includes("Step: 1000")'));
        await evaluate('(()=>{const s=document.querySelector("select[aria-label=误差统计量]");s.value="absolute_error.rms";s.dispatchEvent(new Event("change"))})()');
        assert.ok(await evaluate('document.querySelectorAll(".chart svg")[3].textContent.includes("RMS 绝对误差")'));
        await evaluate('(()=>{const f=document.getElementById("table-filter");f.value="not-a-job";f.dispatchEvent(new Event("input"))})()');
        assert.equal(await evaluate('document.querySelectorAll(".filterable tbody tr:not([hidden])").length'), 0);
        await evaluate('(()=>{const f=document.getElementById("table-filter");f.value="";f.dispatchEvent(new Event("input"))})()');
        await click('全屏');
        assert.ok(await evaluate('document.fullscreenElement!==null'));
        await evaluate('document.exitFullscreen()');
        await call('Page.setDownloadBehavior', {
            behavior: 'allow',
            downloadPath: profile
        });
        await click('导出当前 SVG');
        for (let i = 0; i < 30; i++) {
            if ((await fs.readdir(profile)).includes('chart-01-view.svg')) {
                break;
            }
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        const svg = await fs.readFile(path.join(profile, 'chart-01-view.svg'), 'utf8');
        assert.ok(svg.includes('<svg'));
        assert.equal(await evaluate('new DOMParser().parseFromString(' + JSON.stringify(svg) + ',"image/svg+xml").querySelector("parsererror")===null'), true);
        await fs.mkdir(path.resolve('.inspection'), {
            recursive: true
        });
        await evaluate('document.querySelector(".chart").scrollIntoView()');
        const chartScreenshot = await call('Page.captureScreenshot', {
            format: 'png'
        });
        await fs.writeFile(path.resolve('.inspection/report-chart.png'), Buffer.from(chartScreenshot.data, 'base64'));
        await evaluate('window.scrollTo(0,0)');
        const screenshot = await call('Page.captureScreenshot', {
            format: 'png'
        });
        await fs.writeFile(path.resolve('.inspection/report-desktop.png'), Buffer.from(screenshot.data, 'base64'));
        await call('Emulation.setDeviceMetricsOverride', {
            width: 390,
            height: 844,
            deviceScaleFactor: 1,
            mobile: true
        });
        assert.ok(await evaluate('document.documentElement.scrollWidth <= 390'));
        assert.deepEqual(errors, []);
        console.log(JSON.stringify({
            report,
            charts: 4,
            checks: ['offline load', 'button zoom', 'box zoom', 'pan', 'wheel zoom', 'reset', 'legend', 'log axis', 'hover', 'metric selection', 'table filter', 'fullscreen', 'SVG export', 'mobile width'],
            javascriptErrors: errors.length
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
