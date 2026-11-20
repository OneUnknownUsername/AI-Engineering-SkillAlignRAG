// Dark or light mode. Dark is the default; the choice is remembered in this browser only.
// index.html applies a saved choice before the page draws, so it never flashes the wrong theme.
const KEY = 'skillalignrag-theme';

export function currentTheme() {
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
}

export function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // Storage can be blocked (private window); the theme then lasts until the page is reloaded.
  }
}
