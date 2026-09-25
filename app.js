const state = {
  rows: [],
  verification: {},
  summary: {},
};

const $ = (id) => document.getElementById(id);

const pct = (value) =>
  value == null
    ? "—"
    : `${Math.round(value * 100)}%`;


/* =========================================================
   DATA LOADING
========================================================= */

async function loadJSON(path) {
  const res = await fetch(path, {
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(
      `${path}: ${res.status}`
    );
  }

  return res.json();
}


/* =========================================================
   HELPERS
========================================================= */

function esc(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    })[c]
  );
}


/* =========================================================
   AUTH NORMALIZATION

   Prevents:
   API key / API Key
   OAuth2 / OAuth 2.0
   Basic / Basic Auth
   etc. from appearing as separate categories.
========================================================= */

function normalizeAuthLabel(value) {
  const raw = String(
    value ?? ""
  ).trim();

  const key = raw.toLowerCase();

  const aliases = {
    "api key": "API key",
    "apikey": "API key",

    "oauth2": "OAuth2",
    "oauth 2": "OAuth2",
    "oauth 2.0": "OAuth2",

    // Keep plain "OAuth" separate because
    // it does not necessarily mean OAuth2.
    "oauth": "OAuth",

    "bearer token": "Bearer token",

    "basic": "Basic",
    "basic auth": "Basic",
    "basic authentication": "Basic",

    "jwt": "JWT",
    "json web token": "JWT",

    "client credentials":
      "Client Credentials",

    "client credentials grant":
      "Client Credentials",

    "access token":
      "Access token",

    "authorization token":
      "Authorization token",

    "bot token":
      "Bot token",
  };

  return aliases[key] || raw;
}


function normalizeAuthPairs(pairs) {
  const merged = new Map();

  for (
    const [label, count]
    of pairs || []
  ) {
    const normalized =
      normalizeAuthLabel(label);

    merged.set(
      normalized,
      (
        merged.get(normalized)
        || 0
      ) + count
    );
  }

  return [
    ...merged.entries(),
  ].sort(
    (a, b) => b[1] - a[1]
  );
}


/* =========================================================
   GENERIC COUNTERS

   Used so visible frontend numbers come directly from
   results.json instead of depending on potentially stale
   summary.json values.
========================================================= */

function countValues(
  rows,
  getter
) {
  const counts = new Map();

  for (const row of rows) {
    const value = getter(row);

    const values =
      Array.isArray(value)
        ? value
        : [value];

    for (
      const item
      of values
    ) {
      if (
        item == null
        || item === ""
      ) {
        continue;
      }

      counts.set(
        item,
        (
          counts.get(item)
          || 0
        ) + 1
      );
    }
  }

  return [
    ...counts.entries(),
  ].sort(
    (a, b) => b[1] - a[1]
  );
}


/* =========================================================
   BAR CHARTS
========================================================= */

function renderBars(
  target,
  pairs
) {
  const el = $(target);

  if (!pairs?.length) {
    el.className =
      "bar-list empty-state";

    el.textContent =
      "Run the research agent to populate this chart.";

    return;
  }

  el.className =
    "bar-list";

  const max = Math.max(
    ...pairs.map(
      ([, value]) => value
    ),
    1
  );

  el.innerHTML = pairs
    .slice(0, 7)
    .map(
      ([label, value]) => `
        <div class="bar-row">
          <span
            class="bar-label"
            title="${esc(label)}"
          >
            ${esc(label)}
          </span>

          <span class="bar-bg">
            <span
              class="bar-fill"
              style="width:${
                (value / max) * 100
              }%"
            ></span>
          </span>

          <span class="bar-value">
            ${value}
          </span>
        </div>
      `
    )
    .join("");
}


/* =========================================================
   DERIVED INSIGHTS
========================================================= */

function derivePatterns(rows) {
  const researched =
    rows.filter(
      (r) =>
        r.status === "researched"
    );

  if (
    researched.length < 5
  ) {
    return [];
  }

  const auth = countValues(
    researched,
    (r) =>
      (
        r.auth_methods || []
      ).map(
        normalizeAuthLabel
      )
  );

  const access =
    countValues(
      researched,
      (r) =>
        r.access_model
    );

  const blocker =
    countValues(
      researched,
      (r) =>
        r.main_blocker
    );

  const buildable =
    researched.filter(
      (r) =>
        r.buildability === "yes"
    ).length;

  const gated =
    researched.filter(
      (r) =>
        [
          "admin-gated",
          "partner-gated",
          "contact-sales",
        ].includes(
          r.access_model
        )
    ).length;

  const review =
    researched.filter(
      (r) =>
        !!r.needs_human_review
    ).length;

  const composio =
    researched.filter(
      (r) =>
        !!r.composio_toolkit
    ).length;

  const patterns = [];

  if (auth[0]) {
    patterns.push(
      `${auth[0][0]} is the most common auth pattern in the researched set (${auth[0][1]} apps).`
    );
  }

  if (access[0]) {
    patterns.push(
      `${
        access[0][0]
          .replaceAll("-", " ")
      } is the most common developer-access model (${access[0][1]} apps).`
    );
  }

  patterns.push(
    `${buildable} of ${researched.length} researched apps currently have a documented API + auth path without an obvious integration blocker.`
  );

  if (gated) {
    patterns.push(
      `${gated} apps expose a sales, partner or admin gate — access is a separate problem from API capability.`
    );
  }

  if (blocker[0]) {
    patterns.push(
      `The most repeated blocker is “${blocker[0][0]}” (${blocker[0][1]} apps).`
    );
  }

  if (composio) {
    patterns.push(
      `${composio} researched apps already match a toolkit in the live Composio catalog.`
    );
  }

  if (review) {
    patterns.push(
      `${review} rows remain explicitly flagged for human review instead of being forced into a confident verdict.`
    );
  }

  return patterns.slice(
    0,
    6
  );
}


/* =========================================================
   OVERVIEW
========================================================= */

function renderOverview() {
  const rows =
    state.rows;

  const researched =
    rows.filter(
      (r) =>
        r.status === "researched"
    );

  const buildable =
    researched.filter(
      (r) =>
        r.buildability === "yes"
    ).length;

  const review =
    researched.filter(
      (r) =>
        !!r.needs_human_review
    ).length;

  const composio =
    researched.filter(
      (r) =>
        !!r.composio_toolkit
    ).length;

  const clear =
    researched.length - review;


  /* -------------------------
     TOP METRICS
  ------------------------- */

  $("metricResearched")
    .textContent =
      researched.length;

  $("metricBuildable")
    .textContent =
      researched.length
        ? buildable
        : "—";

  $("metricNeedsReview")
    .textContent =
      researched.length
        ? review
        : "—";

  $("metricComposio")
    .textContent =
      researched.length
        ? composio
        : "—";


  /* -------------------------
     PROGRESS
  ------------------------- */

  const progress =
    rows.length
      ? (
          researched.length
          / rows.length
        )
      : 0;

  $("progressText")
    .textContent =
      `${researched.length} of ${
        rows.length || 100
      } apps researched`;

  $("progressPct")
    .textContent =
      `${Math.round(
        progress * 100
      )}%`;

  $("progressBar")
    .style.width =
      `${progress * 100}%`;


  /* -------------------------
     AUTH PATTERNS
     derived directly from
     results.json
  ------------------------- */

  const authPairs =
    countValues(
      researched,
      (r) =>
        (
          r.auth_methods || []
        ).map(
          normalizeAuthLabel
        )
    );

  renderBars(
    "authBars",
    authPairs
  );


  /* -------------------------
     ACCESS PATTERNS
     also derived directly from
     current results.json
  ------------------------- */

  const accessPairs =
    countValues(
      researched,
      (r) =>
        r.access_model
    );

  renderBars(
    "accessBars",
    accessPairs
  );


  /* -------------------------
     FUNNEL
  ------------------------- */

  $("funnelClear")
    .textContent =
      researched.length
        ? clear
        : "—";

  $("funnelReview")
    .textContent =
      researched.length
        ? review
        : "—";

  $("funnelVerified")
    .textContent =
      state.verification
        ?.sample_size
      || "—";


  /* -------------------------
     AVERAGE CONFIDENCE

     derive from current rows so
     it cannot disagree with UI.
  ------------------------- */

  const confidences =
    researched
      .map(
        (r) =>
          Number(
            r.confidence
          )
      )
      .filter(
        (v) =>
          Number.isFinite(v)
      );

  const averageConfidence =
    confidences.length
      ? (
          confidences.reduce(
            (sum, value) =>
              sum + value,
            0
          )
          / confidences.length
        )
      : null;

  $("confidenceBadge")
    .textContent =
      `Avg confidence ${
        pct(
          averageConfidence
        )
      }`;


  /* -------------------------
     PATTERN CARDS
  ------------------------- */

  const patterns =
    derivePatterns(rows);

  const grid =
    $("patternCards");

  if (
    !patterns.length
  ) {
    $("insightBadge")
      .textContent =
        "Awaiting data";

    grid.innerHTML = `
      <div class="pattern-card muted">
        <span>01</span>
        <p>
          Patterns appear here after enough
          apps have been researched to make
          the counts meaningful.
        </p>
      </div>
    `;

  } else {
    $("insightBadge")
      .textContent =
        `${researched.length} apps analyzed`;

    grid.innerHTML =
      patterns
        .map(
          (pattern, index) => `
            <div class="pattern-card">
              <span>
                ${String(
                  index + 1
                ).padStart(
                  2,
                  "0"
                )}
              </span>

              <p>
                ${esc(pattern)}
              </p>
            </div>
          `
        )
        .join("");
  }
}


/* =========================================================
   VERIFICATION
========================================================= */

function renderVerification() {
  const v =
    state.verification || {};

  $("verifySample")
    .textContent =
      v.sample_size
      || "—";

  $("verifyAgreement")
    .textContent =
      pct(
        v.browser_agreement_rate
      );

  $("verifyHuman")
    .textContent =
      pct(
        v.human_validated_accuracy
      );

  const correctionCount =
    v.claims_contradicted
    ?? v.corrections?.length
    ?? null;

  $("verifyCorrections")
    .textContent =
      correctionCount == null
        ? "—"
        : correctionCount;

  const list =
    $("correctionsList");

  if (
    !v.corrections?.length
  ) {
    list.className =
      "correction-list empty-state";

    list.textContent =
      "No contradictory browser findings were logged in the current verification sample.";

    return;
  }

  list.className =
    "correction-list";

  list.innerHTML =
    v.corrections
      .slice(0, 12)
      .map(
        (c) => `
          <div class="correction-item">

            <div class="correction-app">
              ${esc(
                c.app_name
              )}
            </div>

            <div class="correction-body">

              <strong>
                ${esc(
                  c.field
                )}
              </strong>

              <br>

              ${esc(
                JSON.stringify(
                  c.before
                )
              )}

              →

              ${esc(
                JSON.stringify(
                  c.after
                )
              )}

              ${
                c.reason
                  ? `
                    <br>
                    ${esc(
                      c.reason
                    )}
                  `
                  : ""
              }

            </div>

          </div>
        `
      )
      .join("");
}


/* =========================================================
   FILTER OPTIONS
========================================================= */

function categoryOptions() {
  const categories = [
    ...new Set(
      state.rows
        .map(
          (r) =>
            r.category
        )
        .filter(Boolean)
    ),
  ];

  $("categoryFilter")
    .innerHTML =
      `
        <option value="">
          All categories
        </option>
      `
      +
      categories
        .map(
          (category) => `
            <option
              value="${esc(
                category
              )}"
            >
              ${esc(
                category
              )}
            </option>
          `
        )
        .join("");
}


/* =========================================================
   TABLE HELPERS
========================================================= */

function verdictPill(row) {
  if (
    row.status
    !== "researched"
  ) {
    return `
      <span class="pill pending">
        ${esc(
          row.status
          || "pending"
        )}
      </span>
    `;
  }

  return `
    <span class="pill ${
      esc(
        row.buildability
        || "unknown"
      )
    }">
      ${esc(
        row.buildability
        || "unknown"
      )}
    </span>
  `;
}


function confidenceCell(row) {
  if (
    row.status
      !== "researched"
    || row.confidence == null
  ) {
    return `
      <span class="app-cat">
        —
      </span>
    `;
  }

  const level =
    row.needs_human_review
      ? "review"
      : "clear";

  return `
    <div class="confidence ${level}">
      <strong>
        ${
          Math.round(
            row.confidence
            * 100
          )
        }%
      </strong>

      <span>
        ${
          row.needs_human_review
            ? "review"
            : "clear"
        }
      </span>
    </div>
  `;
}


function methodCell(row) {
  if (
    !row.classification_method
  ) {
    return `
      <span class="app-cat">
        —
      </span>
    `;
  }

  const label =
    row.classification_method
      .replace(
        "deterministic-rules",
        "rules"
      )
      .replace(
        "rules+bazaar-fallback",
        "rules + Bazaar"
      )
      .replace(
        "rules+groq-fallback",
        "rules + Groq"
      )
      .replace(
        "rules+gemini-fallback",
        "rules + Gemini"
      )
      .replace(
        "rules+llm-fallback",
        "rules + LLM"
      )
      .replace(
        "retrieval-failed",
        "retrieval failed"
      );

  return `
    <span class="method-tag">
      ${esc(label)}
    </span>
  `;
}


/* =========================================================
   RESULTS TABLE
========================================================= */

function renderRows() {
  const q =
    $("searchInput")
      .value
      .trim()
      .toLowerCase();

  const category =
    $("categoryFilter")
      .value;

  const build =
    $("buildFilter")
      .value;

  const review =
    $("reviewFilter")
      .value;


  const rows =
    state.rows.filter(
      (r) => {

        const hay =
          JSON.stringify(r)
            .toLowerCase();

        const reviewMatch =
          !review
          ||
          (
            review === "review"
              ? !!r.needs_human_review
              : !r.needs_human_review
          );

        return (
          (
            !q
            || hay.includes(q)
          )
          &&
          (
            !category
            || r.category === category
          )
          &&
          (
            !build
            || r.buildability === build
          )
          &&
          reviewMatch
        );
      }
    );


  $("rowCount")
    .textContent =
      `${rows.length} apps`;


  $("resultsBody")
    .innerHTML =
      rows
        .map(
          (r) => {

            /* -------------------------
               AUTH
            ------------------------- */

            const normalizedAuth =
              [
                ...new Set(
                  (
                    r.auth_methods
                    || []
                  ).map(
                    normalizeAuthLabel
                  )
                ),
              ];

            const auth =
              normalizedAuth.length
                ? normalizedAuth
                    .map(
                      (a) => `
                        <span class="pill">
                          ${esc(a)}
                        </span>
                      `
                    )
                    .join("")
                : `
                    <span class="pill pending">
                      ${
                        r.status
                          === "researched"
                          ? "unknown"
                          : "pending"
                      }
                    </span>
                  `;


            /* -------------------------
               API / MCP
            ------------------------- */

            const api =
              r.api_surface
              || "Pending research";

            const mcp =
              r.mcp_status
                ? `
                    <div class="app-cat">
                      MCP:
                      ${esc(
                        r.mcp_status
                      )}
                    </div>
                  `
                : "";


            /* -------------------------
               EVIDENCE
            ------------------------- */

            const evidence =
              r.evidence?.length
                ? r.evidence
                    .slice(0, 3)
                    .map(
                      (
                        e,
                        index
                      ) => `
                        <a
                          href="${esc(
                            e.url
                          )}"
                          target="_blank"
                          rel="noreferrer"
                          title="${esc(
                            e.supports
                            || "Official evidence"
                          )}"
                        >
                          source ${
                            index + 1
                          } ↗
                        </a>
                      `
                    )
                    .join("")
                : `
                    <span class="app-cat">
                      —
                    </span>
                  `;


            /* -------------------------
               ROW
            ------------------------- */

            return `
              <tr
                class="${
                  r.needs_human_review
                    ? "needs-review-row"
                    : ""
                }"
              >

                <td>
                  <div class="app-name">
                    ${esc(
                      r.name
                    )}
                  </div>

                  <div class="app-cat">
                    ${esc(
                      r.category
                    )}
                  </div>
                </td>

                <td>
                  ${auth}
                </td>

                <td>
                  ${esc(
                    r.access_model
                    || "—"
                  )}
                </td>

                <td>
                  ${esc(api)}
                  ${mcp}
                </td>

                <td>
                  ${verdictPill(r)}
                </td>

                <td>
                  ${confidenceCell(r)}
                </td>

                <td>
                  ${methodCell(r)}
                </td>

                <td>
                  ${esc(
                    r.main_blocker
                    || "—"
                  )}
                </td>

                <td>
                  <div class="evidence-links">
                    ${evidence}
                  </div>
                </td>

              </tr>
            `;
          }
        )
        .join("");
}


/* =========================================================
   BOOT
========================================================= */

async function boot() {
  try {
    const [
      apps,
      researchedRows,
      verification,
      summary,
    ] = await Promise.all([
      loadJSON(
        "/data/apps.json"
      ),

      loadJSON(
        "/data/results.json"
      ),

      loadJSON(
        "/data/verification.json"
      ),

      loadJSON(
        "/data/summary.json"
      ),
    ]);


    /* -------------------------
       MERGE APPS + RESULTS
    ------------------------- */

    const byId =
      new Map(
        researchedRows.map(
          (r) => [
            r.id,
            r,
          ]
        )
      );

    state.rows =
      apps.map(
        (app) =>
          byId.get(app.id)
          ||
          {
            ...app,

            status:
              "pending",

            auth_methods:
              [],

            access_model:
              null,

            api_surface:
              null,

            mcp_status:
              null,

            buildability:
              null,

            main_blocker:
              null,

            confidence:
              null,

            needs_human_review:
              false,

            classification_method:
              null,

            composio_toolkit:
              null,

            evidence:
              [],
          }
      );


    state.verification =
      verification;

    state.summary =
      summary;


    /* -------------------------
       INITIAL RENDER
    ------------------------- */

    categoryOptions();

    renderOverview();

    renderVerification();

    renderRows();


    /* -------------------------
       FILTER EVENTS
    ------------------------- */

    [
      "searchInput",
      "categoryFilter",
      "buildFilter",
      "reviewFilter",
    ].forEach(
      (id) => {

        const eventName =
          id === "searchInput"
            ? "input"
            : "change";

        $(id).addEventListener(
          eventName,
          renderRows
        );
      }
    );

  } catch (err) {
    console.error(err);

    $("progressText")
      .textContent =
        "Could not load research data.";
  }
}


boot();