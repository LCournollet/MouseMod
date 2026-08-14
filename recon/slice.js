// Beautify a byte range of the minified ATK HUB bundle so it can be read.
// usage: node slice.js <startOffset> <length> <outFile>
const fs = require('fs');
const beautify = require('js-beautify').js;

const SRC = 'h:/MouseMod/recon/index-O22l5tpG.js';
const [start, len, out] = [Number(process.argv[2]), Number(process.argv[3]), process.argv[4]];

const text = fs.readFileSync(SRC, 'utf8');
const chunk = text.slice(start, start + len);
const pretty = beautify(chunk, { indent_size: 2, wrap_line_length: 120, brace_style: 'collapse' });
fs.writeFileSync(out, pretty);
console.log(`${out}: ${pretty.length} chars, ${pretty.split('\n').length} lines`);
