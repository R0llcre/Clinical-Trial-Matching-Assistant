import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = join(__dirname, "fixtures");
const PORT = Number(process.env.MOCK_API_PORT || 4100);

const loadFixture = (name) => {
  const raw = readFileSync(join(FIXTURES_DIR, name), "utf-8");
  return JSON.parse(raw);
};

const trialsFixture = loadFixture("trials.json");
const trialDetailFixture = loadFixture("trial_detail_NCT10000001.json");
const previewTokenFixture = loadFixture("preview_token.json");
const createPatientFixture = loadFixture("create_patient.json");
const createMatchFixture = loadFixture("create_match.json");
const matchResultFixture = loadFixture("match_result_match-demo-001.json");

const trialDetailsById = {
  [trialDetailFixture.nct_id]: trialDetailFixture,
};

const status = {
  ok: (data) => ({ ok: true, data }),
  error: (code, message) => ({ ok: false, error: { code, message } }),
};

const sendJson = (res, statusCode, payload) => {
  res.writeHead(statusCode, {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  });
  res.end(JSON.stringify(payload));
};

const readJsonBody = async (req) => {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  if (chunks.length === 0) {
    return null;
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf-8"));
  } catch {
    return null;
  }
};

const toLower = (value) => (value || "").toString().toLowerCase();

const locationPart = (location, indexFromEnd) => {
  const parts = location
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length === 0) {
    return "";
  }
  return toLower(parts[Math.max(0, parts.length - indexFromEnd)]);
};

const filterTrials = (searchParams) => {
  const condition = toLower(searchParams.get("condition"));
  const statusFilter = searchParams.get("status") || "";
  const phaseFilter = searchParams.get("phase") || "";
  const country = toLower(searchParams.get("country"));
  const state = toLower(searchParams.get("state"));
  const city = toLower(searchParams.get("city"));

  let filtered = [...trialsFixture.trials];

  if (condition) {
    filtered = filtered.filter((trial) => {
      const title = toLower(trial.title);
      if (title.includes(condition)) {
        return true;
      }
      return (trial.conditions || []).some((entry) => toLower(entry).includes(condition));
    });
  }

  if (statusFilter) {
    filtered = filtered.filter((trial) => (trial.status || "") === statusFilter);
  }

  if (phaseFilter) {
    filtered = filtered.filter((trial) => (trial.phase || "") === phaseFilter);
  }

  if (country) {
    filtered = filtered.filter((trial) =>
      (trial.locations || []).some((entry) => locationPart(entry, 1) === country)
    );
  }

  if (state) {
    filtered = filtered.filter((trial) =>
      (trial.locations || []).some((entry) => locationPart(entry, 2) === state)
    );
  }

  if (city) {
    filtered = filtered.filter((trial) =>
      (trial.locations || []).some((entry) => locationPart(entry, 3) === city)
    );
  }

  return filtered;
};

const server = createServer(async (req, res) => {
  if (!req.url || !req.method) {
    sendJson(res, 400, status.error("BAD_REQUEST", "Missing request metadata"));
    return;
  }

  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
      "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    });
    res.end();
    return;
  }

  const url = new URL(req.url, `http://${req.headers.host || `127.0.0.1:${PORT}`}`);
  const path = url.pathname;

  if (req.method === "GET" && path === "/health") {
    sendJson(res, 200, status.ok({ healthy: true }));
    return;
  }

  if (req.method === "GET" && path === "/readyz") {
    sendJson(res, 200, status.ok({ ready: true }));
    return;
  }

  if (req.method === "GET" && path === "/api/auth/preview-token") {
    sendJson(res, 200, status.ok(previewTokenFixture));
    return;
  }

  if (req.method === "GET" && path === "/api/trials") {
    const pageRaw = Number(url.searchParams.get("page") || "1");
    const pageSizeRaw = Number(url.searchParams.get("page_size") || "20");
    const page = Number.isFinite(pageRaw) && pageRaw > 0 ? pageRaw : 1;
    const pageSize = Number.isFinite(pageSizeRaw) && pageSizeRaw > 0 ? pageSizeRaw : 20;

    const filtered = filterTrials(url.searchParams);
    const start = (page - 1) * pageSize;
    const pageTrials = filtered.slice(start, start + pageSize);

    sendJson(
      res,
      200,
      status.ok({
        trials: pageTrials,
        total: filtered.length,
        page,
        page_size: pageSize,
      })
    );
    return;
  }

  if (req.method === "GET" && path.startsWith("/api/trials/")) {
    const id = decodeURIComponent(path.slice("/api/trials/".length));
    const trial = trialDetailsById[id];
    if (!trial) {
      sendJson(res, 404, status.error("NOT_FOUND", "Trial not found"));
      return;
    }
    sendJson(res, 200, status.ok(trial));
    return;
  }

  if (req.method === "POST" && path === "/api/patients") {
    const body = await readJsonBody(req);
    if (!body || typeof body !== "object") {
      sendJson(res, 400, status.error("BAD_REQUEST", "Invalid patient payload"));
      return;
    }
    sendJson(res, 200, status.ok(createPatientFixture));
    return;
  }

  if (req.method === "POST" && path === "/api/match") {
    const body = await readJsonBody(req);
    if (!body || typeof body !== "object") {
      sendJson(res, 400, status.error("BAD_REQUEST", "Invalid match payload"));
      return;
    }
    sendJson(res, 200, status.ok(createMatchFixture));
    return;
  }

  if (req.method === "GET" && path.startsWith("/api/matches/")) {
    const auth = req.headers.authorization || "";
    if (!auth.startsWith("Bearer ")) {
      sendJson(res, 401, status.error("UNAUTHORIZED", "Missing bearer token"));
      return;
    }

    const id = decodeURIComponent(path.slice("/api/matches/".length));
    if (id !== matchResultFixture.id) {
      sendJson(res, 404, status.error("NOT_FOUND", "Match not found"));
      return;
    }
    sendJson(res, 200, status.ok(matchResultFixture));
    return;
  }

  sendJson(res, 404, status.error("NOT_FOUND", `No mock route for ${req.method} ${path}`));
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`[mock-api] listening on http://127.0.0.1:${PORT}`);
});
