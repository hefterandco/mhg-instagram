// Turns a Design-canvas artboard (.dc.html) into an Instagram-ready JPEG.
// Usage: node tools/render_artboard.js <artboard.dc.html> <out.jpg> [fontsDir]
// fontsDir holds fraunces-latin-full-normal.woff2 and nunito-sans-latin-full-normal.woff2
// (from the @fontsource-variable packages); without it, Google Fonts is used.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const [src, out, fontsDir] = process.argv.slice(2);
  if (!src || !out) { console.error('usage: render_artboard.js in.dc.html out.jpg [fontsDir]'); process.exit(1); }
  const html = fs.readFileSync(src, 'utf8');
  const helmet = (html.match(/<helmet>([\s\S]*?)<\/helmet>/) || [, ''])[1];
  const body = html.match(/<\/helmet>([\s\S]*?)<\/x-dc>/)[1];
  const props = JSON.parse((html.match(/data-props='([^']*)'/) || [, '{}'])[1]);
  const w = (props.$preview || {}).width || 1080, h = (props.$preview || {}).height || 1350;

  let head = helmet;
  if (fontsDir) {
    const f = n => 'file://' + path.resolve(fontsDir, n);
    head = head.replace(/<link[^>]*fonts\.googleapis[^>]*>/, '') + `<style>
@font-face{font-family:Fraunces;src:url(${f('fraunces-latin-full-normal.woff2')}) format('woff2');font-weight:100 900}
@font-face{font-family:'Nunito Sans';src:url(${f('nunito-sans-latin-full-normal.woff2')}) format('woff2');font-weight:200 1000}
</style>`;
  }
  const page_html = `<!doctype html><html><head><meta charset="utf-8">${head}</head><body style="margin:0"><div id="root" style="width:${w}px;height:${h}px;overflow:hidden">${body}</div></body></html>`;
  const tmp = path.join(path.dirname(path.resolve(out)), '.render-' + path.basename(out) + '.html');
  fs.writeFileSync(tmp, page_html);

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  await page.goto('file://' + tmp);
  await page.evaluate(() => document.fonts.ready);
  await page.locator('#root').screenshot({ path: out, type: 'jpeg', quality: 92 });
  await browser.close();
  fs.unlinkSync(tmp);
  console.log(`${out} (${w}x${h})`);
})();
