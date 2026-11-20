/** A stand-in for `window.matchMedia`, which jsdom lacks. Every query matches or none does:
 * `setWideScreen(true)` makes the layout take its desktop form. */
let wide = false;

export function setWideScreen(value: boolean): void {
  wide = value;
}

export function matchMedia(query: string): MediaQueryList {
  // An EventTarget gives the listener methods; the deprecated addListener/removeListener
  // are left out, so the cast is needed.
  return Object.assign(new EventTarget(), {
    matches: wide,
    media: query,
    onchange: null,
  }) as unknown as MediaQueryList;
}
