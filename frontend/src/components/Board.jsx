import { useState } from "react";
import { Chess } from "chess.js";
import { Chessboard } from "react-chessboard";

// Drag or click to move. chess.js gives instant legal-move feedback here; the backend
// (python-chess) re-checks every move and is the authority (PLAN D16).
// Promotion always picks a queen for now.

const LAST_MOVE = { background: "rgba(235, 205, 90, 0.5)" };
const SELECTED = { background: "rgba(107, 155, 216, 0.55)" };
const TARGET = {
  background: "radial-gradient(circle, rgba(28, 29, 32, 0.35) 22%, transparent 24%)",
};
const CAPTURE_TARGET = {
  background: "radial-gradient(circle, transparent 58%, rgba(28, 29, 32, 0.35) 60%)",
};

function toUci(chess, from, to) {
  const piece = chess.get(from);
  const promotes = piece?.type === "p" && (to[1] === "8" || to[1] === "1");
  return `${from}${to}${promotes ? "q" : ""}`;
}

function isLegal(chess, from, to) {
  return chess.moves({ square: from, verbose: true }).some((m) => m.to === to);
}

export default function Board({ fen, orientation, interactive, lastMove, onMove, arrow }) {
  const [selected, setSelected] = useState(null);
  const chess = new Chess(fen);
  const myColor = orientation === "white" ? "w" : "b";

  function tryMove(from, to) {
    if (!interactive || !to || !isLegal(chess, from, to)) return false;
    setSelected(null);
    onMove(toUci(chess, from, to));
    return true;
  }

  function onSquareClick({ square, piece }) {
    if (!interactive) return;
    if (selected && tryMove(selected, square)) return;
    const mine = piece && piece.pieceType[0] === myColor;
    setSelected(mine && square !== selected ? square : null);
  }

  const squareStyles = {};
  if (lastMove) {
    squareStyles[lastMove.slice(0, 2)] = LAST_MOVE;
    squareStyles[lastMove.slice(2, 4)] = LAST_MOVE;
  }
  if (selected && interactive) {
    squareStyles[selected] = SELECTED;
    for (const m of chess.moves({ square: selected, verbose: true })) {
      squareStyles[m.to] = m.captured ? CAPTURE_TARGET : TARGET;
    }
  }

  return (
    <div className="w-full max-w-[min(88vh,760px)] aspect-square rounded-md overflow-hidden shadow-2xl">
      <Chessboard
        options={{
          id: "main",
          position: fen,
          boardOrientation: orientation,
          allowDragging: interactive,
          canDragPiece: ({ piece }) => interactive && piece.pieceType[0] === myColor,
          onPieceDrop: ({ sourceSquare, targetSquare }) => tryMove(sourceSquare, targetSquare),
          onSquareClick,
          squareStyles,
          arrows: arrow
            ? [{ startSquare: arrow.slice(0, 2), endSquare: arrow.slice(2, 4), color: "#6b9bd8" }]
            : [],
          allowDrawingArrows: false,
          lightSquareStyle: { backgroundColor: "var(--color-sq-light)" },
          darkSquareStyle: { backgroundColor: "var(--color-sq-dark)" },
          animationDurationInMs: 180,
        }}
      />
    </div>
  );
}
