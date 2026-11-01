"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const source=fs.readFileSync(path.join(__dirname,"..","app.js"),"utf8");
assert.ok(!source.includes("function engineTransitionRows("));
assert.ok(!source.includes("renderEngineTransitionExplanation"));
assert.ok(!source.includes("Referencia v0.11: TP"));
const panel={innerHTML:""};
const context={side:"long",money:String,priceText:String,escapeHtml:String,
  timeHorizonLabel:String,elements:{observationalRulesPanel:panel}};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf("const OBSERVATIONAL_RULE_ORDER = ["),
                            source.indexOf("function biasLabel(")),context);
context.renderObservationalRules({side:"long",time_horizon:"intraday_short",snapshot:{stage_rule_traces:{
  intraday_short:[{rule_id:"LIB-CAND-CVD-SLOPE-001",status:"evaluated_shadow",
    outputs:{side_adjusted_normalized_cvd_slope:.1},lab4_correction_input_outputs:["side_adjusted_normalized_cvd_slope"]}]
}}});
assert.ok(panel.innerHTML.includes("Entrada del ajuste probabilístico congelado"));
assert.ok(!panel.innerHTML.includes("Referencia v0.11"));
assert.ok(!panel.innerHTML.includes("Aportación exacta al pronóstico"));
console.log("One selected analysis; no comparison panel: OK");
