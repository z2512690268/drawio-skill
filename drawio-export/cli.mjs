#!/usr/bin/env node
/**
 * draw.io CLI Export Tool
 *
 * Uses the same mechanism as vscode-drawio:
 * loads draw.io's core rendering engine (app.min.js) in a headless browser
 * and communicates via postMessage to export .drawio files to PNG/SVG.
 *
 * Usage:
 *   node cli.mjs input.drawio output.png [options]
 *   node cli.mjs input.drawio output.svg --format svg
 *
 * Options:
 *   --format png|svg    Export format (default: png)
 *   --scale NUMBER      Scale factor (default: 1)
 *   --border NUMBER     Border in pixels (default: 0)
 *   --background COLOR  Page background color (e.g. #FFFFFF for white)
 *   --timeout MS        Timeout in ms (default: 30000)
 *   --no-headless       Show browser window (for debugging)
 */

import { chromium } from 'playwright';
import { createServer } from 'http';
import { existsSync, readFileSync, statSync, writeFileSync } from 'fs';
import { extname, join, normalize, resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DRAWIO_WEBAPP = resolve(__dirname, '../drawio/src/main/webapp');
const EXPORT_HTML = resolve(__dirname, 'export-cli.html');

const MIME_TYPES = {
	'.css': 'text/css',
	'.gif': 'image/gif',
	'.html': 'text/html',
	'.ico': 'image/x-icon',
	'.js': 'text/javascript',
	'.json': 'application/json',
	'.png': 'image/png',
	'.svg': 'image/svg+xml',
	'.txt': 'text/plain',
	'.xml': 'application/xml',
};

function serveFile(res, filePath) {
	if (!existsSync(filePath) || !statSync(filePath).isFile()) {
		res.writeHead(404, { 'Content-Type': 'text/plain' });
		res.end('Not found');
		return;
	}

	res.writeHead(200, { 'Content-Type': MIME_TYPES[extname(filePath)] || 'application/octet-stream' });
	res.end(readFileSync(filePath));
}

function startDrawioServer() {
	return new Promise((resolveServer, reject) => {
		const server = createServer((req, res) => {
			try {
				const url = new URL(req.url || '/', 'http://127.0.0.1');
				const pathname = decodeURIComponent(url.pathname);

				if (pathname === '/' || pathname === '/export-cli.html') {
					serveFile(res, EXPORT_HTML);
					return;
				}

				const relative = normalize(pathname.replace(/^\/+/, ''));
				if (relative.startsWith('..')) {
					res.writeHead(403, { 'Content-Type': 'text/plain' });
					res.end('Forbidden');
					return;
				}

				serveFile(res, join(DRAWIO_WEBAPP, relative));
			} catch (err) {
				res.writeHead(500, { 'Content-Type': 'text/plain' });
				res.end(String(err && err.message || err));
			}
		});

		server.on('error', reject);
		server.listen(0, '127.0.0.1', () => {
			const address = server.address();
			resolveServer({
				server,
				url: `http://127.0.0.1:${address.port}/export-cli.html`,
			});
		});
	});
}

function help() {
	console.error(`draw.io CLI Export Tool
Usage:
  drawio-export input.drawio output.png [options]
  drawio-export input.drawio output.svg --format svg

Options:
  --format png|svg    Export format (default: png)
  --scale NUMBER      Scale factor (default: 1)
  --border NUMBER     Border in pixels (default: 0)
  --timeout MS        Timeout in ms (default: 30000)
  --no-headless       Show browser for debugging

Examples:
  drawio-export diagram.drawio output.png
  drawio-export diagram.drawio output.png --scale 2
  drawio-export diagram.drawio output.svg --format svg`);
}

function parseArgs() {
	const args = process.argv.slice(2);
	if (args.length === 0 || args[0] === '--help' || args[0] === '-h') {
		help();
		process.exit(0);
	}
	if (args.length < 2) {
		help();
		process.exit(1);
	}

	const inputFile = resolve(args[0]);
	const outputFile = resolve(args[1]);
		const opts = { format: 'png', scale: 1, border: 0, background: null, timeout: 30000, headless: true };

	for (let i = 2; i < args.length; i++) {
		switch (args[i]) {
			case '--format': opts.format = args[++i]; break;
			case '--scale': opts.scale = parseFloat(args[++i]); break;
			case '--border': opts.border = parseInt(args[++i]) || 0; break;
			case '--timeout': opts.timeout = parseInt(args[++i]) || 30000; break;
				case '--background': opts.background = args[++i]; break;
			case '--no-headless': opts.headless = false; break;
			default:
				console.error(`Unknown option: ${args[i]}`);
				process.exit(1);
		}
	}
	return { inputFile, outputFile, opts };
}

async function main() {
	const { inputFile, outputFile, opts } = parseArgs();
	console.error(`Reading: ${inputFile}`);

	const formatKey = opts.format === 'svg' ? 'xmlsvg' : 'xmlpng';

	// Read the .drawio XML
		const xmlRaw = readFileSync(inputFile, 'utf-8');
		let xml = xmlRaw;
		if (opts.background) {
			xml = xmlRaw.replace('<mxGraphModel', '<mxGraphModel background="' + opts.background + '"');
}
	if (!xml || xml.length < 10) {
		throw new Error('Input file is empty or too small');
	}

	if (!existsSync(DRAWIO_WEBAPP)) {
		throw new Error(`draw.io webapp not found: ${DRAWIO_WEBAPP}`);
	}

	console.error(`Launching browser...`);
	const drawioServer = await startDrawioServer();
	const browser = await chromium.launch({
		headless: opts.headless,
		args: [
			'--no-sandbox',
			'--disable-setuid-sandbox',
			'--allow-file-access-from-files',
		],
	});

	const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });

	// Suppress harmless OrgChart class redefinition warning
	page.on('console', msg => {
		const text = msg.text();
		if (msg.type() === 'error' && text.includes('OrgChart')) return;
		console.error(`[page ${msg.type()}] ${text}`);
	});
	page.on('pageerror', err => {
		if (err.message.includes('OrgChart')) return;
		console.error(`[page crash] ${err.message}`);
	});

	try {
		console.error(`Loading draw.io engine...`);
		await page.goto(drawioServer.url, {
			waitUntil: 'networkidle',
			timeout: opts.timeout,
		});

		console.error(`Waiting for draw.io init...`);
		await page.waitForFunction(() => window._drawioReady === true, { timeout: opts.timeout });

		const ext = opts.format === 'svg' ? 'svg' : 'png';
		console.error(`Exporting to ${ext.toUpperCase()}...`);

		// Call export inside the page — same postMessage mechanism as vscode-drawio
		const dataUri = await page.evaluate(({ xml, format, scale, border }) => {
			return window.exportDrawio(xml, format, { scale, border });
		}, { xml, format: formatKey, scale: opts.scale, border: opts.border });

		if (!dataUri || typeof dataUri !== 'string') {
			throw new Error('Export returned no data');
		}

		const mime = opts.format === 'svg' ? 'svg+xml' : ext;
		const prefix = `data:image/${mime};base64,`;
		if (!dataUri.startsWith(prefix)) {
			throw new Error(`Unexpected data format: expected ${prefix}...`);
		}

		const buffer = Buffer.from(dataUri.slice(prefix.length), 'base64');
		writeFileSync(outputFile, buffer);
		console.error(`Done: ${outputFile} (${buffer.length} bytes)`);
	} finally {
		await browser.close();
		await new Promise(resolveClose => drawioServer.server.close(resolveClose));
	}
}

main().catch(err => {
	console.error('Error:', err.message);
	process.exit(1);
});
