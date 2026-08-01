import assert from "node:assert/strict";
import test from "node:test";

import { secretsMatch, securityInternals } from "../src/security.js";

test("secret comparison accepts only identical values", () => {
  assert.equal(secretsMatch("abc", "abc"), true);
  assert.equal(secretsMatch("abc", "abd"), false);
  assert.equal(secretsMatch("short", "a much longer value"), false);
});

test("IPv4-mapped addresses are normalized", () => {
  assert.equal(securityInternals.normalizeIp("::ffff:192.168.1.20"), "192.168.1.20");
  assert.equal(securityInternals.normalizeIp("::1"), "127.0.0.1");
});
