/**
 * Live L2 graph reproduce — hits production graph page in Chromium,
 * captures console errors + node/edge counts + error-banner visibility.
 */
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const consoleMsgs = [];
  const pageErrors = [];
  page.on("console", (m) => consoleMsgs.push({ type: m.type(), text: m.text() }));
  page.on("pageerror", (e) => pageErrors.push(String(e)));

  const url = process.env.L2_URL || "https://leadsgenai.in/app/control-center/graph";
  const resp = await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
  console.log("NAV", resp && resp.status(), url);

  // Wait for either counts update, error banner, or timeout
  await page.waitForTimeout(8000);

  const shot = await page.evaluate(() => {
    const counts = document.getElementById("counts");
    const err = document.getElementById("error-banner");
    const loading = document.getElementById("loading");
    const canvas = document.querySelector("#sigma-container canvas");
    return {
      countsText: counts ? counts.textContent : null,
      errorVisible: !!(err && err.classList.contains("vis")),
      errorDetail: (document.getElementById("eb-detail") || {}).textContent || "",
      errorMsg: (document.getElementById("eb-msg") || {}).textContent || "",
      loadingHidden: !!(loading && loading.classList.contains("hidden")),
      hasCanvas: !!canvas,
      canvasW: canvas ? canvas.width : 0,
      canvasH: canvas ? canvas.height : 0,
      globals: {
        graphology: typeof window.graphology,
        Sigma: typeof window.Sigma,
        ELK: typeof window.ELK,
      },
    };
  });

  console.log("SHOT", JSON.stringify(shot, null, 2));
  console.log("PAGE_ERRORS", JSON.stringify(pageErrors, null, 2));
  console.log(
    "CONSOLE_ERR",
    JSON.stringify(
      consoleMsgs.filter((m) => m.type === "error" || /L2 graph|ELK|Sigma|Missing/i.test(m.text)),
      null,
      2
    )
  );

  await browser.close();
  const broken =
    shot.errorVisible ||
    !shot.hasCanvas ||
    (shot.countsText || "").includes("0") && (shot.countsText || "").includes("0 nodes") ||
    pageErrors.length > 0;
  // Parse counts like "42 nodes · 80 edges"
  const m = (shot.countsText || "").match(/(\d+)\s*nodes/i);
  const nodes = m ? parseInt(m[1], 10) : 0;
  console.log("NODES", nodes, "BROKEN_HEURISTIC", broken || nodes === 0);
  process.exit(nodes > 0 && !shot.errorVisible ? 0 : 2);
})().catch((e) => {
  console.error("FATAL", e);
  process.exit(1);
});
