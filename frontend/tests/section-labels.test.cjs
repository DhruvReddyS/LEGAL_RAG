const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
const moduleScope = { exports: {} };
vm.runInNewContext(
  ts.transpileModule(fs.readFileSync('lib/answer-presentation.ts', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText,
  moduleScope,
);
const { presentAnswer } = moduleScope.exports;

// Every heading the backend can write, per role. Mirrors
// backend/app/agents/response_generation.py ROLE_SECTION_LABELS, which has a
// test pinning the same strings. The two lists are deliberately duplicated
// rather than shared: there is no build step joining these repositories, and
// a silent divergence is exactly what both tests exist to prevent.
const BACKEND_HEADINGS = {
  citizen: {
    legal_basis: 'Why this is the legal position',
    application: 'How this applies to you',
    next_step: 'What you can do now',
    limit: 'Important limits',
  },
  police: {
    legal_basis: 'Governing provision and legal basis',
    application: 'Application to this matter',
    next_step: 'Required procedural steps',
    limit: 'Safeguards, limits and uncertainties',
  },
  advocate: {
    legal_basis: 'Authority and legal basis',
    application: 'Application to these facts',
    next_step: 'Steps available',
    limit: 'Contrary considerations, limits and gaps',
  },
};

function render(role, category) {
  const heading = BACKEND_HEADINGS[role][category];
  return presentAnswer(
    `## Direct answer\n\nThe governing provision applies.\n\n` +
      `## ${heading}\n\nBODY-${category.toUpperCase()}`,
  );
}

for (const role of Object.keys(BACKEND_HEADINGS)) {
  test(`${role}: the limits section is routed to limits, not into the answer`, () => {
    // The misclassification that changes what a reader believes. A caveat
    // rendered inside the answer body reads as part of the answer.
    const result = render(role, 'limit');
    assert.match(result.limits, /BODY-LIMIT/);
    assert.doesNotMatch(result.other, /BODY-LIMIT/);
  });

  test(`${role}: the legal basis section is routed to basis`, () => {
    const result = render(role, 'legal_basis');
    assert.match(result.basis, /BODY-LEGAL_BASIS/);
  });

  test(`${role}: the application section is routed to basis`, () => {
    const result = render(role, 'application');
    assert.match(result.basis, /BODY-APPLICATION/);
  });

  test(`${role}: the next-step section stays in the answer body`, () => {
    // Practical steps belong in the body. Routing them to limits or the
    // footer would bury the part a reader most needs to act on.
    const result = render(role, 'next_step');
    assert.match(result.other, /BODY-NEXT_STEP/);
    assert.doesNotMatch(result.limits, /BODY-NEXT_STEP/);
    assert.doesNotMatch(result.footer, /BODY-NEXT_STEP/);
  });

  test(`${role}: no heading is mistaken for the currency footer`, () => {
    for (const category of Object.keys(BACKEND_HEADINGS[role])) {
      const result = render(role, category);
      assert.doesNotMatch(
        result.footer,
        new RegExp(`BODY-${category.toUpperCase()}`),
        `${role}/${category} was pushed below the answer into the footer`,
      );
    }
  });
}
