// localStorage service for persisting user-specific data

const STORAGE_KEYS = {
  ORG_STATS: "s3drive_org_stats",
  RECENT_FILES: "s3drive_recent_files",
};

const ORG_STATS_TTL = 5 * 60 * 1000; // 5 minutes
const RECENT_FILES_TTL = 7 * 24 * 60 * 60 * 1000; // 7 days

export function getOrgStats(orgId) {
  try {
    const data = localStorage.getItem(STORAGE_KEYS.ORG_STATS);
    if (!data) return null;
    const parsed = JSON.parse(data);
    const orgData = parsed?.[orgId];
    if (!orgData) return null;
    // Check if data is stale
    if (Date.now() - orgData.timestamp > ORG_STATS_TTL) return null;
    return orgData;
  } catch {
    return null;
  }
}

export function setOrgStats(orgId, stats) {
  try {
    const data = localStorage.getItem(STORAGE_KEYS.ORG_STATS);
    const parsed = data ? JSON.parse(data) : {};
    parsed[orgId] = {
      ...stats,
      timestamp: Date.now(),
    };
    localStorage.setItem(STORAGE_KEYS.ORG_STATS, JSON.stringify(parsed));
  } catch (e) {
    console.error("Failed to save org stats:", e);
  }
}

export function getRecentFiles() {
  try {
    const data = localStorage.getItem(STORAGE_KEYS.RECENT_FILES);
    if (!data) return [];
    const parsed = JSON.parse(data);
    // Filter out stale entries
    const now = Date.now();
    return parsed.filter((f) => now - f.timestamp < RECENT_FILES_TTL);
  } catch {
    return [];
  }
}

export function addRecentFile(file) {
  try {
    const data = localStorage.getItem(STORAGE_KEYS.RECENT_FILES);
    const parsed = data ? JSON.parse(data) : [];
    // Remove if already exists
    const filtered = parsed.filter((f) => f.key !== file.key);
    // Add to beginning
    filtered.unshift({ ...file, timestamp: Date.now() });
    // Keep only last 10
    localStorage.setItem(STORAGE_KEYS.RECENT_FILES, JSON.stringify(filtered.slice(0, 10)));
  } catch (e) {
    console.error("Failed to save recent file:", e);
  }
}

export function clearRecentFiles() {
  try {
    localStorage.removeItem(STORAGE_KEYS.RECENT_FILES);
  } catch (e) {
    console.error("Failed to clear recent files:", e);
  }
}
