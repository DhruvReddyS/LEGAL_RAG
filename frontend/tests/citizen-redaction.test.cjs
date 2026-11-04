const test = require('node:test');
const assert = require('node:assert/strict');
const { loadTs } = require('./helpers/load-ts.cjs');
const { detectSensitive, applyMasks, segments, countByKind } = loadTs('lib/citizen-redact.ts');

const kinds = text => detectSensitive(text).map(span => [span.kind, span.value]);

test('finds Aadhaar however it is grouped, and not numbers that cannot be one', () => {
  assert.deepEqual(kinds('Aadhaar 2345 6789 0123 here'), [['aadhaar', '2345 6789 0123']]);
  assert.deepEqual(kinds('uid 234567890123.'), [['aadhaar', '234567890123']]);
  assert.deepEqual(kinds('reference 123456789012'), [], 'Aadhaar never starts with 0 or 1');
});

test('finds a PAN in either case', () => {
  assert.deepEqual(kinds('PAN ABCDE1234F'), [['pan', 'ABCDE1234F']]);
  assert.deepEqual(kinds('pan abcde1234f'), [['pan', 'abcde1234f']]);
});

test('finds Indian phone numbers with or without the prefix', () => {
  for (const phone of ['9876543210', '+91 98765 43210', '098765-43210']) {
    const [span] = detectSensitive(`call ${phone} now`);
    assert.equal(span.kind, 'phone');
    assert.equal(span.value, phone);
  }
  assert.deepEqual(kinds('case 1234567890'), [], 'a mobile number starts with 6 to 9');
});

test('finds email', () => {
  assert.deepEqual(kinds('write to ramesh.k@example.co.in please'), [['email', 'ramesh.k@example.co.in']]);
});

test('an account number needs a label, because it has no shape of its own', () => {
  assert.deepEqual(kinds('A/C No: 50100234567890'), [['account', '50100234567890']]);
  assert.deepEqual(kinds('Account number 1234567890'), [['account', '1234567890']]);
  assert.deepEqual(kinds('खाता संख्या 1234567890'), [['account', '1234567890']]);
  assert.deepEqual(kinds('Cheque no 123456'), [], 'a cheque number is what the tool needs to read');
});

test('finds a card number and an IFSC', () => {
  assert.deepEqual(kinds('card 4111 1111 1111 1111'), [['account', '4111 1111 1111 1111']]);
  assert.deepEqual(kinds('IFSC HDFC0001234'), [['account', 'HDFC0001234']]);
});

test('finds addresses by label and by shape', () => {
  assert.deepEqual(kinds('Address: 14, Lake View Colony, Hyderabad'), [['address', '14, Lake View Colony, Hyderabad']]);
  const lines = detectSensitive('H.No 4-5 Gandhi Road\nHyderabad').map(span => span.kind);
  assert.deepEqual(lines, ['address']);
});

test('a phone inside an address line stays visible as its own detail, and both are masked', () => {
  const text = 'Address: 14 Main Road, ph 9876543210, Hyderabad';
  const spans = detectSensitive(text);
  assert.ok(spans.some(span => span.kind === 'phone'));
  assert.ok(spans.some(span => span.kind === 'address'));
  const masked = applyMasks(text, spans);
  assert.equal(masked.includes('9876543210'), false);
  assert.equal(masked.includes('14 Main Road'), false);
});

test('ordinary legal text is left alone', () => {
  assert.deepEqual(kinds('Section 138 of the Act. Dated 12/01/2026. Rs. 45,000/- within 15 days.'), []);
});

test('masking replaces what was found and nothing else', () => {
  const text = 'PAN ABCDE1234F and call 9876543210 today';
  const out = applyMasks(text, detectSensitive(text));
  assert.equal(out, 'PAN [PAN REMOVED] and call [PHONE REMOVED] today');
});

test('a detail the person chose to keep stays', () => {
  const text = 'PAN ABCDE1234F and call 9876543210';
  const spans = detectSensitive(text).map(span => span.kind === 'phone' ? { ...span, masked: false } : span);
  assert.equal(applyMasks(text, spans), 'PAN [PAN REMOVED] and call 9876543210');
});

test('a manual mask is applied, and overlapping masks do not corrupt the text', () => {
  const text = 'Mr Ramesh Kumar PAN ABCDE1234F end';
  const spans = detectSensitive(text);
  assert.equal(applyMasks(text, spans, [{ start: 3, end: 15 }]), 'Mr [REMOVED] PAN [PAN REMOVED] end');
  const start = text.indexOf('PAN');
  assert.equal(applyMasks(text, spans, [{ start, end: start + 8 }]), 'Mr Ramesh Kumar [REMOVED] end');
});

test('segments put back exactly the original text', () => {
  const text = 'A 9876543210 B ABCDE1234F C';
  const parts = segments(text, detectSensitive(text));
  assert.equal(parts.map(part => part.text).join(''), text);
  assert.equal(parts.filter(part => part.span).length, 2);
});

test('counts by kind', () => {
  assert.deepEqual(countByKind(detectSensitive('9876543210 and 9123456780, ABCDE1234F')), { phone: 2, pan: 1 });
});
