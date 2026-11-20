// Helpers for showing a cited quote inside its page text.

// "slide 21" for slide decks, "page 4" otherwise.
export function pageLabel(sourceFile, page) {
  return /\.(pptx?|key)$/i.test(sourceFile || '') ? `slide ${page}` : `page ${page}`;
}

// Split the page text into before / quote / after. Without a located quote, all text is "before".
export function splitAround(text, highlight) {
  if (!highlight) return { before: text, match: '', after: '' };
  const [start, end] = highlight;
  return { before: text.slice(0, start), match: text.slice(start, end), after: text.slice(end) };
}

// A short preview: about `radius` characters each side of the quote, cut at word boundaries,
// with line breaks collapsed so it reads as one passage.
export function snippet(text, highlight, radius = 160) {
  const flat = (s) => s.replace(/\s+/g, ' ');
  if (!highlight) {
    const start = flat(text).trim();
    return { before: start.length > radius * 2 ? `${start.slice(0, radius * 2).replace(/\s\S*$/, '')}…` : start, match: '', after: '' };
  }
  const { before, match, after } = splitAround(text, highlight);
  let head = flat(before);
  let tail = flat(after);
  if (head.length > radius) head = `…${head.slice(-radius).replace(/^\S*\s/, '')}`;
  if (tail.length > radius) tail = `${tail.slice(0, radius).replace(/\s\S*$/, '')}…`;
  return { before: head, match: flat(match), after: tail };
}
