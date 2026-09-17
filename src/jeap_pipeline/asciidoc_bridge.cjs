// Asciidoctor owns the grammar and include expansion. Only diagram macros are intercepted.
const fs = require('node:fs');
const path = require('node:path');
const asciidoctor = require('@asciidoctor/core')();
require('@asciidoctor/docbook-converter').register();

const root = fs.realpathSync(process.argv[2]);
const entry = process.argv[3];
const diagrams = [];
const logger = asciidoctor.MemoryLogger.create();
asciidoctor.LoggerManager.setLogger(logger);
const registry = asciidoctor.Extensions.create();
registry.blockMacro(function () {
  this.named('plantuml');
  this.process(function (parent, target) {
    const directory = parent.getDocument().getBaseDir();
    const file = fs.realpathSync(path.resolve(directory, target));
    if (!file.startsWith(root + path.sep)) {
      throw new Error(`Diagram leaves the input directory: ${target}`);
    }
    const token = `JEAPDIAGRAM${diagrams.length}END`;
    diagrams.push({token, source: fs.readFileSync(file, 'utf8')});
    return this.createParagraph(parent, token, {});
  });
});

try {
  const docbook = asciidoctor.convertFile(path.join(root, entry), {
    backend: 'docbook5', standalone: true, to_file: false, safe: 'safe',
    base_dir: root, extension_registry: registry,
    attributes: {showtitle: false, 'max-include-depth': 32},
  });
  const messages = logger.getMessages();
  if (messages.length) {
    throw new Error(messages.map(message => message.getText()).join('\n'));
  }
  process.stdout.write(JSON.stringify({docbook, diagrams}));
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
