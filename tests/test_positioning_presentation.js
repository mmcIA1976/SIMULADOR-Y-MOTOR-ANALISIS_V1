"use strict";
// Isolated runtime check: no DOM, network, app startup or database writes.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname,"..","app.js"),"utf8");
const context = { side:"long", money:(v)=>String(v), priceText:(v)=>String(v) };
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf("const OBSERVATIONAL_RULE_ORDER = ["),
                            source.indexOf("function renderObservationalRules(")),context);
assert.equal(context.observationNumber(null),null);
assert.equal(context.observationNumber(""),null);
assert.equal(context.observationNumber(0),0);
assert.equal(context.observationTimestamp(undefined),"--");
const trace = (rule,outputs)=>({rule_id:rule,status:"evaluated_shadow",outputs});
const view = (rule,outputs)=>context.observationRuleView(trace(rule,outputs),{});
const oi = view("M4-RULE-OPEN-INTEREST-CHANGE-001",{
  dOI_H:Math.log(1.01),oi_previous:100,oi_current:101,end_ms:1790420700000});
assert.equal(oi.tone,"contexto");
assert.equal(oi.metrics[0].value,"+1.000%");
const funding = view("M4-RULE-FUNDING-STATE-001",{
  last_settled_funding_rate:.00005,settled_funding_rate_per_hour:.00000625,
  observed_interval_hours:8,funding_time_ms:1790409600001});
assert.equal(funding.metrics[0].value,"+0.00500%");
assert.equal(funding.metrics[1].value,"+0.000625%");
assert.match(funding.verdict,/no es la próxima tasa/);
const legacy = view("M4-RULE-FUNDING-STATE-001",{last_funding_rate:.0001,interval_hours:8});
assert.match(legacy.title,/contrato anterior/);
assert.equal(legacy.metrics[0].value,"+0.01000%");
const blocked = context.observationRuleView({rule_id:"M4-RULE-OPEN-INTEREST-CHANGE-001",
  status:"blocked",outputs:{},reason_codes:["exact_oi_endpoints_unavailable"]},{});
assert.equal(blocked.tone,"bloqueada");
const absorption = view("LIB-CAND-ABSORPTION-001",{
  side_adjusted_ATI_H:.5,side_adjusted_horizon_displacement_atr:.8,
  flow_opposing_wick_ratio:.3,relative_horizon_volume:1.2});
assert.equal(absorption.tone,"contexto");
assert.match(absorption.verdict,/No prueba absorción/);
console.log("Positioning presentation runtime checks: OK");
