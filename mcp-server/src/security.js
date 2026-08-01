import { createHash, timingSafeEqual } from "node:crypto";

function digest(value) {
  return createHash("sha256").update(String(value), "utf8").digest();
}

export function secretsMatch(actual, expected) {
  return timingSafeEqual(digest(actual), digest(expected));
}

function normalizeIp(value) {
  const address = String(value || "").trim();
  if (address.startsWith("::ffff:")) {
    return address.slice(7);
  }
  return address === "::1" ? "127.0.0.1" : address;
}

function requestCredential(request) {
  const apiKey = request.get("x-api-key");
  if (apiKey) {
    return apiKey;
  }

  const authorization = request.get("authorization") || "";
  const match = /^Bearer\s+(.+)$/i.exec(authorization);
  return match ? match[1] : "";
}

export function createAccessMiddleware(config) {
  const allowedIps = new Set(config.allowedIps.map(normalizeIp));

  return (request, response, next) => {
    if (request.path === "/health") {
      next();
      return;
    }

    if (allowedIps.size > 0) {
      const remoteIp = normalizeIp(request.socket.remoteAddress);
      if (!allowedIps.has(remoteIp)) {
        response.status(403).json({ error: "Client IP is not allowed." });
        return;
      }
    }

    const credential = requestCredential(request);
    if (!credential || !secretsMatch(credential, config.apiKey)) {
      response.set("WWW-Authenticate", 'Bearer realm="codesys-mcp"');
      response.status(401).json({ error: "Authentication required." });
      return;
    }

    next();
  };
}

export function createHostValidationMiddleware(config) {
  const loopbackHosts = ["127.0.0.1", "localhost", "::1"];
  const configuredHosts =
    config.allowedHosts.length > 0
      ? config.allowedHosts
      : loopbackHosts.includes(config.host)
        ? loopbackHosts
        : [];
  const allowedHosts = new Set(configuredHosts.map((host) => host.toLowerCase()));

  return (request, response, next) => {
    if (allowedHosts.size === 0) {
      next();
      return;
    }

    const hostname = String(request.hostname || "").toLowerCase();
    if (!allowedHosts.has(hostname)) {
      response.status(421).json({ error: "Host header is not allowed." });
      return;
    }
    next();
  };
}

export const securityInternals = {
  normalizeIp,
  requestCredential,
};
