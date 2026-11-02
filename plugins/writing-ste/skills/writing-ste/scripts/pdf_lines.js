// Extract each line of text of a PDF with its position, with macOS PDFKit.
// Output: "=== PAGE n ===" before each page, then "x<TAB>y<TAB>text" for each line.
// Usage: osascript -l JavaScript pdf_lines.js <input.pdf> <output.txt>
ObjC.import('PDFKit');
ObjC.import('Foundation');

function run(argv) {
  var doc = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0]));
  var n = doc.pageCount;
  var out = [];
  for (var i = 0; i < n; i++) {
    var page = doc.pageAtIndex(i);
    out.push('=== PAGE ' + (i + 1) + ' ===');
    var sel = page.selectionForRect(page.boundsForBox(0));  // 0: the media box
    if (!sel || sel.isNil()) continue;
    var lines = sel.selectionsByLine;
    for (var j = 0; j < lines.count; j++) {
      var line = lines.objectAtIndex(j);
      var r = line.boundsForPage(page);
      out.push(Math.round(r.origin.x) + '\t' + Math.round(r.origin.y) + '\t' + ObjC.unwrap(line.string));
    }
  }
  $(out.join('\n')).writeToFileAtomicallyEncodingError(argv[1], true, $.NSUTF8StringEncoding, null);
  return n;
}
