# Import necessary libraries
import chess # Still useful for board representation and move parsing
from flask import Flask, request, jsonify
from flask_cors import CORS
import math
import random
import time
import asyncio # For running async route (Flask[async])
import traceback # Import for detailed error logging
import sys # NEW: Import for setting recursion limit

# Set a higher recursion limit to prevent RecursionError for deep searches
sys.setrecursionlimit(2000) # Increased from default (often 1000) to 2000

# Initialize Flask app
app = Flask(__name__)
# Enable CORS for all routes, allowing requests from your frontend
CORS(app)

# --- AI Configuration and Piece Values (Translated from JS) ---
PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000 # King value is high for checkmate
}

# Piece-Square Tables (mirrored for black pieces in evaluation)
# These are for White's perspective; black's values will be flipped.
PAWN_TABLE = [
    [0, 0, 0, 0, 0, 0, 0, 0],
    [50, 50, 50, 50, 50, 50, 50, 50],
    [10, 10, 20, 30, 30, 20, 10, 10],
    [5, 5, 10, 25, 25, 10, 5, 5],
    [0, 0, 0, 0, 0, 0, 0, 0],
    [5, -5, -10, 0, 0, -10, -5, 5],
    [5, 10, 10, -20, -20, 10, 10, 5],
    [0, 0, 0, 0, 0, 0, 0, 0]
]

KNIGHT_TABLE = [
    [-50, -40, -30, -30, -30, -30, -40, -50],
    [-40, -20, 0, 0, 0, 0, -20, -40],
    [-30, 0, 10, 15, 15, 10, 0, -30],
    [-30, 5, 15, 20, 20, 15, 5, -30],
    [-30, 0, 15, 20, 20, 15, 0, -30],
    [-30, 5, 10, 15, 15, 10, 5, -30],
    [-40, -20, 0, 5, 5, 0, -20, -40],
    [-50, -40, -30, -30, -30, -30, -30, -50]
]

BISHOP_TABLE = [
    [-20, -10, -10, -10, -10, -10, -10, -20],
    [-10, 0, 0, 0, 0, 0, 0, -10],
    [-10, 0, 5, 10, 10, 5, 0, -10],
    [-10, 5, 5, 10, 10, 5, 5, -10],
    [-10, 0, 10, 10, 10, 10, 0, -10],
    [-10, 10, 10, 10, 10, 10, 10, -10],
    [-10, 5, 0, 0, 0, 0, 5, -10],
    [-20, -10, -10, -10, -10, -10, -10, -20]
]

ROOK_TABLE = [
    [0, 0, 0, 0, 0, 0, 0, 0],
    [5, 10, 10, 10, 10, 10, 10, 5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [0, 0, 0, 5, 5, 0, 0, 0]
]

QUEEN_TABLE = [
    [-20, -10, -10, -5, -5, -10, -10, -20],
    [-10, 0, 0, 0, 0, 0, 0, -10],
    [-10, 0, 5, 5, 5, 5, 0, -10],
    [-5, 0, 5, 5, 5, 5, 0, -5],
    [0, 0, 5, 5, 5, 5, 0, -5],
    [-10, 5, 5, 5, 5, 5, 0, -10],
    [-10, 0, 5, 0, 0, 0, 0, -10],
    [-20, -10, -10, -5, -5, -10, -10, -20]
]

KING_TABLE = [
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-20, -30, -30, -40, -40, -30, -30, -20],
    [-10, -20, -20, -20, -20, -20, -20, -10],
    [20, 20, 0, 0, 0, 0, 20, 20],
    [20, 30, 10, 0, 0, 10, 30, 20]
]

KING_ENDGAME_TABLE = [
    [-50, -40, -30, -20, -20, -30, -40, -50],
    [-30, -20, -10, 0, 0, -10, -20, -30],
    [-30, -10, 20, 30, 30, 20, -10, -30],
    [-30, -10, 30, 40, 40, 30, -10, -30],
    [-30, -10, 30, 40, 40, 30, -10, -30],
    [-30, -10, 20, 30, 30, 20, -10, -30],
    [-30, -30, 0, 0, 0, 0, -30, -30],
    [-50, -30, -30, -30, -30, -30, -30, -50]
]

# Map chess.Piece types to their tables
PIECE_TABLES = {
    chess.PAWN: PAWN_TABLE,
    chess.KNIGHT: KNIGHT_TABLE,
    chess.BISHOP: BISHOP_TABLE,
    chess.ROOK: ROOK_TABLE,
    chess.QUEEN: QUEEN_TABLE,
    chess.KING: KING_TABLE
}

# Transposition Table
transposition_table = {}
TT_EXACT = 0
TT_LOWERBOUND = 1
TT_UPPERBOUND = 2

# --- AI Helper Functions ---

def get_piece_table(piece_type, color, board_state):
    """Returns the correct piece-square table, flipped for black if needed."""
    table = PIECE_TABLES.get(piece_type)
    if not table:
        return None

    # Flip table for black pieces
    if color == chess.BLACK:
        # Create a new list of lists, where each inner list is reversed
        flipped_table = [row[::-1] for row in reversed(table)]
        return flipped_table
    return table

def _is_path_clear(board, square1, square2):
    """
    Checks if there are any pieces between square1 and square2.
    Assumes square1 and square2 are on the same rank or file.
    This replaces chess.squares_between due to reported issues.
    """
    file1, rank1 = chess.square_file(square1), chess.square_rank(square1)
    file2, rank2 = chess.square_file(square2), chess.square_rank(square2)

    if rank1 == rank2:  # Same rank
        start_file = min(file1, file2) + 1
        end_file = max(file1, file2)
        for f in range(start_file, end_file):
            if board.piece_at(chess.square(f, rank1)):
                return False
    elif file1 == file2:  # Same file
        start_rank = min(rank1, rank2) + 1
        end_rank = max(rank1, rank2)
        for r in range(start_rank, end_rank):
            if board.piece_at(chess.square(file1, r)):
                return False
    # For diagonals, if needed, this function would need more logic.
    # For rook connection, we only care about ranks/files.
    return True

# Helper function to check if a rank or file coordinate is valid (0-7)
def _is_valid_coord(coord):
    return 0 <= coord <= 7

def _is_passed_pawn(board, square, pawn_color):
    """
    Checks if a pawn at 'square' is a passed pawn for 'pawn_color'.
    A pawn is passed if there are no opposing pawns in its file or adjacent files
    on its way to promotion.
    """
    file_idx = chess.square_file(square)
    rank_idx = chess.square_rank(square)
    
    opponent_color = chess.BLACK if pawn_color == chess.WHITE else chess.WHITE

    # Determine the direction of pawn advancement
    if pawn_color == chess.WHITE:
        # For white, ranks increase (from 0 to 7) as pawn advances
        # We need to check ranks higher than the current pawn's rank
        start_rank_check = rank_idx + 1
        end_rank_check = 8 # Up to rank 7 (index 7)
        direction_step = 1
    else: # black pawn
        # For black, ranks decrease (from 7 to 0) as pawn advances
        # We need to check ranks lower than the current pawn's rank
        start_rank_check = rank_idx - 1
        end_rank_check = -1 # Down to rank 0 (index 0)
        direction_step = -1

    # Check current file and adjacent files
    for f in range(max(0, file_idx - 1), min(8, file_idx + 2)):
        # Iterate through ranks in the pawn's advancement direction
        r = start_rank_check
        while (pawn_color == chess.WHITE and r < end_rank_check) or \
              (pawn_color == chess.BLACK and r > end_rank_check):
            
            target_square = chess.square(f, r)
            piece = board.piece_at(target_square)

            if piece and piece.piece_type == chess.PAWN and piece.color == opponent_color:
                return False # Opposing pawn found, not a passed pawn
            r += direction_step
    return True # No opposing pawns found in the way

def evaluate_board(board, ai_color_is_white):
    """Evaluates the given board state from the AI's perspective."""
    score = 0
    ai_color = chess.WHITE if ai_color_is_white else chess.BLACK
    opponent_color = chess.BLACK if ai_color_is_white else chess.WHITE

    white_bishops = 0
    black_bishops = 0

    # Piece values (material) and Piece-Square Tables (positional)
    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece:
            piece_type = piece.piece_type
            piece_color = piece.color
            value = PIECE_VALUES.get(piece_type, 0)

            # Get row and column for piece-square tables
            row, col = chess.square_rank(square), chess.square_file(square)

            table = get_piece_table(piece_type, piece_color, board)
            positional_value = table[row][col] if table else 0

            if piece_color == ai_color:
                score += value + positional_value
            else:
                score -= (value + positional_value)

            # Count bishops for bishop pair bonus
            if piece_type == chess.BISHOP:
                if piece_color == chess.WHITE:
                    white_bishops += 1
                else:
                    black_bishops += 1

            # Mobility bonus (number of pseudo-legal moves)
            temp_board_for_mobility = board.copy()
            temp_board_for_mobility.turn = piece_color # Set turn for pseudo-legal moves calculation
            mobility_bonus = len(list(temp_board_for_mobility.legal_moves)) * 2

            if piece_color == ai_color:
                score += mobility_bonus
            else:
                score -= mobility_bonus

            # Piece Safety / Hanging Pieces (simplified check)
            if board.is_attacked_by(opponent_color, square) and not board.is_attacked_by(piece_color, square):
                if piece_color == ai_color:
                    score -= value * 0.8
                else:
                    score += value * 0.8

    # Bishop Pair Bonus
    if white_bishops >= 2:
        score += 30 if ai_color_is_white else -30
    if black_bishops >= 2:
        score += 30 if not ai_color_is_white else -30

    # Rook Connection/Battery
    rook_connection_bonus = 10
    white_rooks = []
    black_rooks = []

    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece and piece.piece_type == chess.ROOK:
            if piece.color == chess.WHITE:
                white_rooks.append(square)
            else:
                black_rooks.append(square)
    
    # Check for rook connection using the custom _is_path_clear function
    if len(white_rooks) >= 2:
        for i in range(len(white_rooks)):
            for j in range(i + 1, len(white_rooks)):
                sq1, sq2 = white_rooks[i], white_rooks[j]
                if chess.square_rank(sq1) == chess.square_rank(sq2): # Same rank
                    if _is_path_clear(board, sq1, sq2):
                        score += (rook_connection_bonus if ai_color_is_white else -rook_connection_bonus)
                elif chess.square_file(sq1) == chess.square_file(sq2): # Same file
                    if _is_path_clear(board, sq1, sq2):
                        score += (rook_connection_bonus if not ai_color_is_white else -rook_connection_bonus)

    if len(black_rooks) >= 2:
        for i in range(len(black_rooks)):
            for j in range(i + 1, len(black_rooks)):
                sq1, sq2 = black_rooks[i], black_rooks[j]
                if chess.square_rank(sq1) == chess.square_rank(sq2): # Same rank
                    if _is_path_clear(board, sq1, sq2):
                        score += (rook_connection_bonus if not ai_color_is_white else -rook_connection_bonus)
                elif chess.square_file(sq1) == chess.square_file(sq2): # Same file
                    if _is_path_clear(board, sq1, sq2):
                        score += (rook_connection_bonus if not ai_color_is_white else -rook_connection_bonus)


    # Pawn Structure (doubled, isolated, connected, passed)
    for file_index in range(8):
        pawns_in_file_white = sum(1 for rank in range(8) if board.piece_at(chess.square(file_index, rank)) == chess.Piece(chess.PAWN, chess.WHITE))
        pawns_in_file_black = sum(1 for rank in range(8) if board.piece_at(chess.square(file_index, rank)) == chess.Piece(chess.PAWN, chess.BLACK))

        # Doubled pawns
        if pawns_in_file_white > 1:
            score += -20 if ai_color_is_white else 20
        if pawns_in_file_black > 1:
            score += -20 if not ai_color_is_white else 20

        # Isolated pawns
        is_isolated_white = pawns_in_file_white > 0 and \
                            (file_index == 0 or sum(1 for rank in range(8) if board.piece_at(chess.square(file_index - 1, rank)) == chess.Piece(chess.PAWN, chess.WHITE)) == 0) and \
                            (file_index == 7 or sum(1 for rank in range(8) if board.piece_at(chess.square(file_index + 1, rank)) == chess.Piece(chess.PAWN, chess.WHITE)) == 0)
        if is_isolated_white:
            score += -15 if ai_color_is_white else 15

        is_isolated_black = pawns_in_file_black > 0 and \
                            (file_index == 0 or sum(1 for rank in range(8) if board.piece_at(chess.square(file_index - 1, rank)) == chess.Piece(chess.PAWN, chess.BLACK)) == 0) and \
                            (file_index == 7 or sum(1 for rank in range(8) if board.piece_at(chess.square(file_index + 1, rank)) == chess.Piece(chess.PAWN, chess.BLACK)) == 0)
        if is_isolated_black:
            score += -15 if not ai_color_is_white else 15
        
        # Connected Pawns (simplified - just checks for adjacent pawns)
        for rank_index in range(8):
            pawn = board.piece_at(chess.square(file_index, rank_index))
            if pawn and pawn.piece_type == chess.PAWN:
                if file_index > 0 and board.piece_at(chess.square(file_index - 1, rank_index)) == chess.Piece(chess.PAWN, pawn.color):
                    score += 5 if (pawn.color == ai_color) else -5
                if file_index < 7 and board.piece_at(chess.square(file_index + 1, rank_index)) == chess.Piece(chess.PAWN, pawn.color):
                    score += 5 if (pawn.color == ai_color) else -5


    # King Safety (Pawn Shield) - Enhanced
    king_safety_bonus = 10
    king_attack_penalty = 50
    king_open_file_penalty = 10

    king_square_white = board.king(chess.WHITE)
    king_square_black = board.king(chess.BLACK)

    if king_square_white:
        white_king_safety = 0
        white_king_rank, white_king_file = chess.square_rank(king_square_white), chess.square_file(king_square_white)
        # Check pawns in front of white king (ranks 1 and 2 from white's perspective)
        for f in range(max(0, white_king_file - 1), min(8, white_king_file + 2)):
            # Check rank - 1
            target_rank_1 = white_king_rank - 1
            if _is_valid_coord(target_rank_1) and board.piece_at(chess.square(f, target_rank_1)) == chess.Piece(chess.PAWN, chess.WHITE):
                white_king_safety += 10
            # Check rank - 2
            target_rank_2 = white_king_rank - 2
            if _is_valid_coord(target_rank_2) and board.piece_at(chess.square(f, target_rank_2)) == chess.Piece(chess.PAWN, chess.WHITE):
                white_king_safety += 5
        
        # Check if king is on an open file
        if not any(board.piece_at(chess.square(white_king_file, r)) == chess.Piece(chess.PAWN, chess.WHITE) for r in range(8)):
            score -= king_open_file_penalty # Penalty for open file in front of king

        if board.is_check():
            if ai_color_is_white:
                score -= king_attack_penalty # Penalty if AI's king is in check
            else:
                score += king_attack_penalty # Bonus if opponent's king is in check

        score += white_king_safety if ai_color_is_white else -white_king_safety

    if king_square_black:
        black_king_safety = 0
        black_king_rank, black_king_file = chess.square_rank(king_square_black), chess.square_file(king_square_black)
        # Check pawns in front of black king (ranks 6 and 5 from black's perspective)
        for f in range(max(0, black_king_file - 1), min(8, black_king_file + 2)):
            # Check rank + 1
            target_rank_1 = black_king_rank + 1
            if _is_valid_coord(target_rank_1) and board.piece_at(chess.square(f, target_rank_1)) == chess.Piece(chess.PAWN, chess.BLACK):
                black_king_safety += 10
            # Check rank + 2
            target_rank_2 = black_king_rank + 2
            if _is_valid_coord(target_rank_2) and board.piece_at(chess.square(f, target_rank_2)) == chess.Piece(chess.PAWN, chess.BLACK):
                black_king_safety += 5
        
        # Check if king is on an open file
        if not any(board.piece_at(chess.square(black_king_file, r)) == chess.Piece(chess.PAWN, chess.BLACK) for r in range(8)):
            score -= king_open_file_penalty # Penalty for open file in front of king

        if board.is_check():
            if not ai_color_is_white:
                score -= king_attack_penalty # Penalty if AI's king is in check
            else:
                score += king_attack_penalty # Bonus if opponent's king is in check
        
        score += black_king_safety if not ai_color_is_white else -black_king_safety

    # Center Control
    central_squares = [
        chess.D4, chess.E4,
        chess.D5, chess.E5
    ]
    center_control_bonus = 10
    for square in central_squares:
        piece = board.piece_at(square)
        if piece:
            if piece.color == ai_color:
                score += center_control_bonus
            else:
                score -= center_control_bonus

    # Development (Early Game) - Simplified
    # Only for first 10 half-moves (5 full moves)
    if board.fullmove_number < 6:
        white_developed_pieces = 0
        black_developed_pieces = 0

        # Check white knights and bishops not on starting rank
        for square in [chess.B1, chess.C1, chess.F1, chess.G1]: # B1, C1, F1, G1 are typical starting squares
            piece = board.piece_at(square)
            if piece and piece.color == chess.WHITE and piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
                pass # Still on starting square
            elif piece is None:
                pass # Empty square
            else: # Piece is white, not on starting square, and is a knight/bishop
                if piece.color == chess.WHITE and piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
                    white_developed_pieces += 1

        # Check black knights and bishops not on starting rank
        for square in [chess.B8, chess.C8, chess.F8, chess.G8]: # B8, C8, F8, G8 are typical starting squares
            piece = board.piece_at(square)
            if piece and piece.color == chess.BLACK and piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
                pass # Still on starting square
            elif piece is None:
                pass # Empty square
            else: # Piece is black, not on starting square, and is a knight/bishop
                if piece.color == chess.BLACK and piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
                    black_developed_pieces += 1

        if ai_color_is_white:
            score += (white_developed_pieces * 10) - (black_developed_pieces * 10)
        else:
            score += (black_developed_pieces * 10) - (white_developed_pieces * 10)


    # Rook on Open/Semi-Open Files
    rook_open_semi_file_bonus = 15
    for file_idx in range(8):
        file_is_open_white = True
        file_is_open_black = True
        has_white_rook = False
        has_black_rook = False

        for rank_idx in range(8): # Corrected range(8)
            square = chess.square(file_idx, rank_idx)
            piece = board.piece_at(square)
            if piece:
                if piece.piece_type == chess.PAWN:
                    if piece.color == chess.WHITE: file_is_open_white = False
                    else: file_is_open_black = False
                elif piece.piece_type == chess.ROOK:
                    if piece.color == chess.WHITE: has_white_rook = True
                    else: has_black_rook = True
        
        if has_white_rook and file_is_open_white and file_is_open_black: # Truly open file
            score += (rook_open_semi_file_bonus if ai_color_is_white else -rook_open_semi_file_bonus)
        elif has_white_rook and file_is_open_black: # Semi-open (no black pawns)
            score += (rook_open_semi_file_bonus / 2 if ai_color_is_white else -rook_open_semi_file_bonus / 2)

        if has_black_rook and file_is_open_black and file_is_open_white: # Truly open file
            score += (rook_open_semi_file_bonus if not ai_color_is_white else -rook_open_semi_file_bonus)
        elif has_black_rook and file_is_open_white: # Semi-open (no white pawns)
            score += (rook_open_semi_file_bonus / 2 if not ai_color_is_white else -rook_open_semi_file_bonus / 2)

    # Passed Pawns
    passed_pawn_base_bonus = 50
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece and piece.piece_type == chess.PAWN:
            # Replaced board.is_passed_pawn with custom _is_passed_pawn
            if _is_passed_pawn(board, sq, piece.color):
                rank = chess.square_rank(sq)
                advancement_bonus = 0
                if piece.color == chess.WHITE:
                    advancement_bonus = (rank - 1) * 10 # 2nd rank pawn has 0 bonus, 7th rank has 50
                else:
                    advancement_bonus = (6 - rank) * 10 # 7th rank pawn has 0 bonus, 2nd rank has 50
                
                if piece.color == ai_color:
                    score += passed_pawn_base_bonus + advancement_bonus
                else:
                    score -= (passed_pawn_base_bonus + advancement_bonus)
    
    # Knight Outposts
    knight_outpost_bonus = 25
    central_squares = [chess.D4, chess.E4, chess.D5, chess.E5]
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece and piece.piece_type == chess.KNIGHT:
            knight_color = piece.color
            
            # Check if it's a central square
            if sq in central_squares:
                # Check if defended by a friendly pawn
                is_defended_by_pawn = False
                for pawn_sq in board.attackers(knight_color, sq):
                    p = board.piece_at(pawn_sq)
                    if p and p.piece_type == chess.PAWN and p.color == knight_color:
                        is_defended_by_pawn = True
                        break
                
                # Check if attacked by an opponent's pawn
                is_attacked_by_opp_pawn = False
                opp_color = chess.BLACK if knight_color == chess.WHITE else chess.WHITE
                for pawn_sq in board.attackers(opp_color, sq):
                    p = board.piece_at(pawn_sq)
                    if p and p.piece_type == chess.PAWN and p.color == opp_color:
                        is_attacked_by_opp_pawn = True
                        break

                if is_defended_by_pawn and not is_attacked_by_opp_pawn:
                    if knight_color == ai_color:
                        score += knight_outpost_bonus
                    else:
                        score -= knight_outpost_bonus


    return score

# Transposition Table
transposition_table = {}
TT_EXACT = 0
TT_LOWERBOUND = 1
TT_UPPERBOUND = 2

# Quiescence Search
def quiescence_search(board, ai_color_is_white, alpha, beta):
    # nodes_evaluated += 1 # Global counter in real engine
    
    # Stand-pat evaluation
    stand_pat = evaluate_board(board, ai_color_is_white)

    if stand_pat >= beta:
        return beta
    if stand_pat > alpha:
        alpha = stand_pat

    # Generate only "noisy" moves (captures, checks, promotions)
    # python-chess has a `board.is_capture(move)` and `board.gives_check(move)`
    # Promotions are implied by the move itself (e.g., e7e8q)
    noisy_moves = []
    for move in board.legal_moves:
        if board.is_capture(move) or board.gives_check(move) or move.promotion:
            noisy_moves.append(move)

    # Sort noisy moves by MVL/LVA for better pruning
    noisy_moves.sort(key=lambda move: calculate_mvl_lva(board, move), reverse=True) # Higher is better for MVL/LVA

    for move in noisy_moves:
        board.push(move)
        score = -quiescence_search(board, not ai_color_is_white, -beta, -alpha) # Negamax
        board.pop()

        if score >= beta:
            return beta
        if score > alpha:
            alpha = score
            
    return alpha

# Minimax with Alpha-Beta Pruning
def minimax(board, depth, ai_color_is_white, alpha, beta):
    # Check transposition table
    fen = board.fen()
    if fen in transposition_table:
        stored_depth, stored_score, flag = transposition_table[fen]
        if stored_depth >= depth:
            if flag == TT_EXACT:
                return stored_score
            if flag == TT_LOWERBOUND and stored_score >= beta:
                return stored_score
            if flag == TT_UPPERBOUND and stored_score <= alpha:
                return stored_score
    
    if depth == 0:
        # Enter quiescence search at depth 0
        score = quiescence_search(board, ai_color_is_white, alpha, beta)
        transposition_table[fen] = (depth, score, TT_EXACT)
        return score

    if board.is_checkmate():
        # Score for checkmate should be very high, but depends on who delivers it.
        # If the AI delivers checkmate, it's a huge positive score.
        # If the opponent delivers checkmate, it's a huge negative score.
        if board.turn == (chess.WHITE if ai_color_is_white else chess.BLACK):
             # Current player (opponent) is checkmated, so it's AI's win
            score = 1000000 # AI wins
        else:
            # AI is checkmated, so it's AI's loss
            score = -1000000 # AI loses
        transposition_table[fen] = (depth, score, TT_EXACT)
        return score
    elif board.is_stalemate() or board.is_insufficient_material() or board.is_fivefold_repetition() or board.is_seventyfive_moves():
        score = 0
        transposition_table[fen] = (depth, score, TT_EXACT)
        return score

    best_score_for_node = float('-inf') if ai_color_is_white else float('inf')
    flag = TT_LOWERBOUND if ai_color_is_white else TT_UPPERBOUND

    # Get legal moves and sort them for better alpha-beta pruning
    legal_moves = list(board.legal_moves)
    # Sort moves by MVL/LVA and checks first
    legal_moves.sort(key=lambda move: calculate_mvl_lva(board, move) + (100 if board.gives_check(move) else 0), reverse=True) # Higher is better

    for move in legal_moves:
        board.push(move)
        # Call minimax for the opponent's turn (negamax approach)
        score = minimax(board, depth - 1, not ai_color_is_white, -beta, -alpha) # Negamax with alpha-beta
        board.pop() # Undo the move

        if ai_color_is_white: # Maximizing player
            if score > best_score_for_node:
                best_score_for_node = score
            alpha = max(alpha, score)
        else: # Minimizing player
            if score < best_score_for_node:
                best_score_for_node = score
            beta = min(beta, score)

        if beta <= alpha:
            # Cutoff occurred, so the value is a bound, not an exact score.
            # If current player is maximizing, it's a lower bound (we found a move
            # that's at least 'best_score_for_node').
            # If current player is minimizing, it's an upper bound (we found a move
            # that's at most 'best_score_for_node').
            flag = TT_LOWERBOUND if ai_color_is_white else TT_UPPERBOUND
            break # Alpha-beta cutoff

    transposition_table[fen] = (depth, best_score_for_node, flag) # Store score with correct flag
    return best_score_for_node

def calculate_mvl_lva(board, move):
    """Calculates Most Valuable Victim - Least Valuable Attacker for move ordering."""
    if not board.is_capture(move):
        return 0 # No capture, no MVL/LVA value

    victim_piece = board.piece_at(move.to_square)
    attacker_piece = board.piece_at(move.from_square)

    if not victim_piece or not attacker_piece:
        return 0 # Should not happen for a capture

    victim_value = PIECE_VALUES.get(victim_piece.piece_type, 0)
    attacker_value = PIECE_VALUES.get(attacker_piece.piece_type, 0)

    # Prioritize capturing higher value pieces with lower value pieces
    return victim_value - attacker_value


# --- API Endpoint ---
@app.route('/api/get_ai_move', methods=['POST'])
async def get_ai_move(): # Make the route function 'async'
    """
    API endpoint to get the best move from the AI (custom minimax).
    Request body:
    {
        "board_fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "ai_color": "black", // "white" or "black"
        "difficulty": "hard" // "easy", "intermediate", "hard"
    }
    Response body:
    {
        "success": true,
        "move": {
            "from_square": "e7", // e.g., "e2"
            "to_square": "e5",   // e.g., "e4"
            "promotion": "q"     // optional, e.g., "q", "r", "b", "n"
        },
        "message": "AI found a move."
    }
    """
    data = request.get_json()
    board_fen = data.get('board_fen')
    ai_color_str = data.get('ai_color')
    difficulty = data.get('difficulty')

    if not board_fen or not ai_color_str or not difficulty:
        return jsonify({"success": False, "message": "Missing board_fen, ai_color, or difficulty"}), 400

    try:
        # Initialize the chess board from FEN
        board = chess.Board(board_fen)
        ai_is_white = (ai_color_str.lower() == 'white')
        
        # Check if the game is already over
        if board.is_game_over():
            return jsonify({"success": False, "message": "Game is already over (checkmate, stalemate, or draw)"}), 200

        # Ensure it's AI's turn based on ai_color_str and board.turn
        # chess.Board.turn is a boolean (True for white, False for black)
        expected_turn = chess.WHITE if ai_color_str.lower() == 'white' else chess.BLACK
        if board.turn != expected_turn:
             return jsonify({"success": False, "message": "Not AI's turn to move."}), 200

        # Define search depth based on difficulty
        # Reduced depths for improved performance. Deeper search means longer wait times.
        if difficulty == 'easy':
            depth = 1 # Increased from 0 to allow at least one move search + quiescence
        elif difficulty == 'intermediate':
            depth = 2
        elif difficulty == 'hard':
            depth = 3 # Adjusted to prevent hitting recursion limit frequently
        else:
            depth = 2 # Default for unknown difficulty

        # Clear transposition table for a fresh search (optional, depends on caching strategy)
        transposition_table.clear()

        # Perform the AI search using our custom minimax
        best_score = float('-inf') if ai_is_white else float('inf')
        best_move = None
        
        legal_moves_for_ai = list(board.legal_moves)
        
        if not legal_moves_for_ai:
            return jsonify({"success": False, "message": "No legal moves for AI (checkmate/stalemate)"}), 200

        # Sort moves for better alpha-beta pruning (MVL/LVA + checks)
        legal_moves_for_ai.sort(key=lambda move: calculate_mvl_lva(board, move) + (100 if board.gives_check(move) else 0), reverse=True)

        for move in legal_moves_for_ai:
            board.push(move)
            # Call minimax for the opponent's turn (negamax approach)
            score = minimax(board, depth - 1, not ai_is_white, -math.inf, math.inf)
            board.pop() # Undo the move

            if ai_is_white: # Maximizing player
                if score > best_score:
                    best_score = score
                    best_move = move
            else: # Minimizing player
                if score < best_score:
                    best_score = score
                    best_move = move

        if best_move:
            response_move = {
                # UCI format: "e2e4", "g1f3", "e7e8q" (from_square, to_square, promotion if any)
                "from_square": best_move.uci()[0:2],
                "to_square": best_move.uci()[2:4],
                "promotion": best_move.promotion.name.lower() if best_move.promotion else None
            }
            return jsonify({"success": True, "move": response_move, "message": "AI found a move."}), 200
        else:
            return jsonify({"success": False, "message": "AI could not find a move."}), 200

    except Exception as e:
        app.logger.error(f"Error processing AI move: {e}")
        app.logger.error(traceback.format_exc()) # Log full traceback for detailed debugging
        return jsonify({"success": False, "message": str(e)}), 500

# Run the Flask app
if __name__ == '__main__':
    import asyncio
    # Using '0.0.0.0' makes the server accessible from other devices on your network.
    # For local development, '127.0.0.1' or 'localhost' also works.
    asyncio.run(app.run(debug=True, host='0.0.0.0', port=5000))