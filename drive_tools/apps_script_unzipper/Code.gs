const ROOT_FOLDER = 'Book Twins';
const BOOKS_FOLDER = 'books';

function doGet() {
  return HtmlService.createHtmlOutput(html_())
    .setTitle('Book Twin Drive Unzipper')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

function unzipBookTwin(zipUrlOrId, customName) {
  const fileId = extractFileId_(zipUrlOrId);
  if (!fileId) throw new Error('Non ries