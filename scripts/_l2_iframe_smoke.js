/**
 * Reproduce L2 empty inside control-center parent iframe (the real user path).
 */
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const consoleMsgs = [];
  const pageErrors = [];
  page.on("console", (m) => consoleMsgs.push({ type: m.type(), text: m.text() }));
  page.on("pageerror", (e) => pageErrors.push(String(e)));

  // Control center uses client-side hash/route for L2 stack
  const url = process.env.CC_URL || "https://leadsgenai.in/app/control-center#stack";
  const resp = await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
  console.log("NAV", resp && resp.status(), url);

  // Click L2 rail if present
  const l2 = await page.$("#rail-l2, [data-route=stack], button:has-text('L2')");
  if (l2) {
    await l2.click();
    console.log("CLICKED L2 rail");
  } else {
    console.log("NO L2 rail found — dump buttons");
    const texts = await page.evaluate(() =>
      Array.from(document.querySelectorAll("button,.rail-item,[data-route]"))
        .slice(0, 40)
        .map((el) => ({
          tag: el.tagName,
          id: el.id,
          route: el.getAttribute("data-route"),
          text: (el.textContent || "").trim().slice(0, 60),
        }))
    );
    console.log("UI", JSON.stringify(texts, null, 2));
  }

  await page.waitForTimeout(5000);

  const parent = await page.evaluate(() => {
    const frame = document.getElementById("cc-graph-frame");
    const canvas = document.getElementById("canvas");
    return {
      hasFrame: !!frame,
      frameSrc: frame ? frame.getAttribute("src") : null,
      frameW: frame ? frame.clientWidth : 0,
      frameH: frame ? frame.clientHeight : 0,
      canvasHTML: canvas ? canvas.innerHTML.slice(0, 500) : null,
      bodyText: (document.body.innerText || "").slice(0, 400),
    };
  });
  console.log("PARENT", JSON.stringify(parent, null, 2));

  let iframeShot = null;
  const frame = page.frameLocator("#cc-graph-frame");
  try {
    await page.waitForSelector("#cc-graph-frame", { timeout: 10000 });
    // access content frame
    const fh = await page.$("#cc-graph-frame");
    const cf = await fh.contentFrame();
    if (cf) {
      await cf.waitForTimeout(6000);
      iframeShot = await cf.evaluate(() => {
        const counts = document.getElementById("counts");
        const err = document.getElementById("error-banner");
        const loading = document.getElementById("loading");
        const canvas = document.querySelector("#sigma-container canvas");
        return {
          countsText: counts ? counts.textContent : null,
          errorVisible: !!(err && err.classList.contains("vis")),
          errorDetail: (document.getElementById("eb-detail") || {}).textContent || "",
          loadingHidden: !!(loading && loading.classList.contains("hidden")),
          hasCanvas: !!canvas,
          canvasW: canvas ? canvas.width : 0,
          canvasH: canvas ? canvas.height : 0,
          url: location.href,
        };
      });
    } else {
      iframeShot = { error: "no contentFrame — likely XFO/CSP blocked" };
    }
  } catch (e) {
    iframeShot = { error: String(e) };
  }

  console.log("IFRAME", JSON.stringify(iframeShot, null, 2));
  console.log("PAGE_ERRORS", JSON.stringify(pageErrors, null, 2));
  console.log(
    "CONSOLE",
    JSON.stringify(
      consoleMsgs.filter((m) => m.type === "error" || /frame|L2|graph|Refused/i.test(m.text)).slice(0, 30),
      null,
      2
    )
  );

  await browser.close();
  const nodes = iframeShot && iframeShot.countsText
    ? parseInt((iframeShot.countsText.match(/(\d+)\s*nodes/i) || [0, 0])[1], 10)
    : 0;
  process.exit(nodes > 0 && iframeShot && !iframeShot.errorVisible ? 0 : 2);
})().catch((e) => {
  console.error("FATAL", e);
  process.exit(1);
});
