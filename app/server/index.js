import express from 'express';
import multer from 'multer';
import path from 'path';
import mammoth from 'mammoth';
import pdfParse from 'pdf-parse/lib/pdf-parse.js';
import TurndownService from 'turndown';
import nlp from 'compromise';

const app = express();
const port = process.env.PORT || 3000;

const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 25 * 1024 * 1024 } });

app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));

const publicDir = path.join(process.cwd(), 'app', 'public');
app.use(express.static(publicDir));

const turndown = new TurndownService();

function normalizeNewlines(text) {
  return text.replace(/\r\n?/g, '\n');
}

function chunkParagraphs(text) {
  const lines = normalizeNewlines(text).split('\n');
  const parts = [];
  let buffer = [];
  for (const line of lines) {
    if (line.trim() === '') {
      if (buffer.length) {
        parts.push(buffer.join(' ').trim());
        buffer = [];
      }
    } else {
      buffer.push(line.trim());
    }
  }
  if (buffer.length) parts.push(buffer.join(' ').trim());
  return parts.join('\n\n');
}

function buildRedactionMapFromNER(text, userCompanyNames, userKeyPeople) {
  const doc = nlp(text);
  const people = Array.from(new Set(doc.people().out('array')));
  const orgs = Array.from(new Set(doc.organizations().out('array')));

  const explicitPeople = (userKeyPeople || []).filter(Boolean);
  const explicitOrgs = (userCompanyNames || []).filter(Boolean);

  const redactionMap = new Map();

  let personIndex = 1;
  let orgIndex = 1;

  for (const name of people) {
    if (!redactionMap.has(name)) {
      redactionMap.set(name, `[PERSON_${personIndex++}]`);
    }
  }
  for (const name of orgs) {
    if (!redactionMap.has(name)) {
      redactionMap.set(name, `[ORG_${orgIndex++}]`);
    }
  }

  for (const name of explicitPeople) {
    if (name && !redactionMap.has(name)) {
      redactionMap.set(name, `[PERSON_${personIndex++}]`);
    }
  }
  for (const name of explicitOrgs) {
    if (name && !redactionMap.has(name)) {
      redactionMap.set(name, `[ORG_${orgIndex++}]`);
    }
  }

  return redactionMap;
}

function redactWithMap(text, redactionMap) {
  let result = text;
  // Sort by length desc to avoid partial overlaps
  const entries = Array.from(redactionMap.entries()).sort((a, b) => b[0].length - a[0].length);
  for (const [target, token] of entries) {
    if (!target) continue;
    const escaped = target.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const pattern = new RegExp(`(?<![\w-])${escaped}(?![\w-])`, 'gi');
    result = result.replace(pattern, token);
  }
  return result;
}

function redactEmails(text) {
  const emailRegex = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi;
  return text.replace(emailRegex, '[REDACTED_EMAIL]');
}

function anonymize(text, options = {}) {
  const { companyNames = [], keyPeople = [], removeEmails = true } = options;
  let output = text;
  if (removeEmails) {
    output = redactEmails(output);
  }
  const redactionMap = buildRedactionMapFromNER(output, companyNames, keyPeople);
  output = redactWithMap(output, redactionMap);
  return output;
}

async function extractToMarkdown(file) {
  const { originalname, buffer } = file;
  const ext = path.extname(originalname).toLowerCase();
  try {
    if (ext === '.docx') {
      const { value: html } = await mammoth.convertToHtml({ buffer });
      const md = turndown.turndown(html || '');
      return md;
    }
    if (ext === '.pdf') {
      const data = await pdfParse(buffer);
      const text = data.text || '';
      const md = chunkParagraphs(text);
      return md;
    }
    if (ext === '.md' || ext === '.markdown' || ext === '.txt') {
      return buffer.toString('utf8');
    }
    // Fallback: try UTF-8 text
    return buffer.toString('utf8');
  } catch (err) {
    return `Extraction failed for ${originalname}: ${err.message || String(err)}`;
  }
}

app.post('/api/process', upload.array('files'), async (req, res) => {
  try {
    const mode = (req.body.mode || 'batch').toLowerCase();
    const removeEmails = (req.body.removeEmails || 'true') === 'true';

    const companyNames = Array.isArray(req.body.companyNames)
      ? req.body.companyNames
      : (req.body.companyNames ? String(req.body.companyNames).split(',').map(s => s.trim()).filter(Boolean) : []);

    const keyPeople = Array.isArray(req.body.keyPeople)
      ? req.body.keyPeople
      : (req.body.keyPeople ? String(req.body.keyPeople).split(',').map(s => s.trim()).filter(Boolean) : []);

    const files = req.files || [];
    if (!files.length) {
      return res.status(400).json({ error: 'No files uploaded' });
    }

    const perFile = [];
    for (const file of files) {
      const extracted = await extractToMarkdown(file);
      const anonymized = anonymize(extracted, { companyNames, keyPeople, removeEmails });
      const header = `# ${file.originalname}`;
      const body = anonymized.trim();
      const markdown = `${header}\n\n${body}\n`;
      perFile.push({ filename: file.originalname, markdown });
    }

    let combinedMarkdown = '';
    if (mode === 'batch') {
      combinedMarkdown = perFile.map(f => f.markdown).join('\n\n---\n\n');
    }

    res.json({
      mode,
      files: perFile,
      combinedMarkdown,
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message || String(err) });
  }
});

app.get('/health', (_req, res) => {
  res.json({ ok: true });
});

app.get('*', (_req, res) => {
  res.sendFile(path.join(publicDir, 'index.html'));
});

app.listen(port, () => {
  console.log(`Server listening on http://localhost:${port}`);
});