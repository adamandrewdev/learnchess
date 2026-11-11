import { defaultPieces } from "react-chessboard";

// Board and piece appearance, chosen in the Controls panel and remembered per browser.
// Green boards are left out on purpose: green is reserved for "good move" (PLAN D13).

export const BOARD_THEMES = {
  brown: { label: "Brown", light: "#efd9b5", dark: "#b58863" },
  slate: { label: "Slate blue", light: "#dee3e6", dark: "#8ca2ad" },
  grey: { label: "Grey", light: "#e6e6e6", dark: "#8e9099" },
  lavender: { label: "Lavender", light: "#e6e0ef", dark: "#9f90b0" },
};

// Piece styles reuse the library's own piece drawings and add a CSS filter, so black
// pieces keep a visible edge on dark squares and white ones on light squares.
const FILTERS = {
  classic: null,
  outlined: {
    w: "drop-shadow(0 0 1px rgba(0,0,0,0.85))",
    b: "drop-shadow(0 0 1px rgba(255,255,255,0.95)) drop-shadow(0 0 1px rgba(255,255,255,0.6))",
  },
  shadowed: {
    w: "drop-shadow(0 0 1px rgba(0,0,0,0.6)) drop-shadow(0 2px 2px rgba(0,0,0,0.45))",
    b: "drop-shadow(0 0 1px rgba(255,255,255,0.7)) drop-shadow(0 2px 2px rgba(0,0,0,0.45))",
  },
};

export const PIECE_STYLES = {
  classic: { label: "Classic" },
  outlined: { label: "Outlined" },
  shadowed: { label: "Outlined + shadow" },
};

function styledPieces(filters) {
  if (!filters) return defaultPieces;
  return Object.fromEntries(
    Object.entries(defaultPieces).map(([key, render]) => [
      key,
      (props) => render({ ...props, svgStyle: { ...props?.svgStyle, filter: filters[key[0]] } }),
    ]),
  );
}

// Built once at load: the board renders each entry as a component, so they must be stable.
const PIECE_SETS = Object.fromEntries(
  Object.entries(FILTERS).map(([name, filters]) => [name, styledPieces(filters)]),
);

export const DEFAULT_BOARD = "slate";
export const DEFAULT_PIECES = "outlined";

export function boardTheme(name) {
  return BOARD_THEMES[name] ?? BOARD_THEMES[DEFAULT_BOARD];
}

export function pieceSet(name) {
  return PIECE_SETS[name] ?? PIECE_SETS[DEFAULT_PIECES];
}
