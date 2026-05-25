"""
Blog Backend Data Management System
SQLite + dark Tkinter GUI | Python 3.8+
Optional: pip install reportlab
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from typing import Any, List, Optional, Tuple

DB_NAME = "blog.db"
POSTS_PER_PAGE = 5
PASSWORD_MIN_LEN = 6

THEME = {
    "bg": "#0d1117",
    "surface": "#161b22",
    "card": "#21262d",
    "border": "#30363d",
    "accent": "#a371f7",
    "text": "#e6edf3",
    "muted": "#8b949e",
    "success": "#3fb950",
    "danger": "#f85149",
    "input": "#0d1117",
}


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def valid_email(email: str) -> bool:
    return bool(re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email.strip()))


def valid_username(username: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9_]{3,30}$", username.strip()))


# =============================================================================
# DATABASE
# =============================================================================
class Database:
    def __init__(self, path: str = DB_NAME) -> None:
        self.path = path
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'User',
                    bio TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    author_id INTEGER NOT NULL,
                    category TEXT NOT NULL DEFAULT 'General',
                    tags TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    likes INTEGER NOT NULL DEFAULT 0,
                    dislikes INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL,
                    user_id INTEGER,
                    commenter_name TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS post_votes (
                    user_id INTEGER NOT NULL,
                    post_id INTEGER NOT NULL,
                    vote_type TEXT NOT NULL CHECK (vote_type IN ('like', 'dislike')),
                    PRIMARY KEY (user_id, post_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
                );
                """
            )
            row = conn.execute(
                "SELECT id FROM users WHERE username = ?", ("admin",)
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO users (username, email, password, role, bio, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "admin",
                        "admin@blog.local",
                        hash_password("Admin@123"),
                        "Admin",
                        "System administrator",
                        now_str(),
                    ),
                )


# =============================================================================
# SERVICES
# =============================================================================
class UserService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def register(
        self, username: str, email: str, password: str, bio: str = ""
    ) -> Tuple[bool, str]:
        if not valid_username(username):
            return False, "Username: 3-30 chars (letters, numbers, underscore)."
        if not valid_email(email):
            return False, "Invalid email."
        if len(password) < PASSWORD_MIN_LEN:
            return False, "Password must be at least %d characters." % PASSWORD_MIN_LEN
        try:
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO users (username, email, password, role, bio, created_at)
                    VALUES (?, ?, ?, 'User', ?, ?)
                    """,
                    (
                        username.strip(),
                        email.strip().lower(),
                        hash_password(password),
                        bio.strip(),
                        now_str(),
                    ),
                )
            return True, "Registration successful."
        except sqlite3.IntegrityError:
            return False, "Username or email already exists."
        except sqlite3.Error as e:
            return False, str(e)

    def login(self, username: str, password: str) -> Tuple[bool, str, Optional[dict]]:
        try:
            with self.db.connect() as conn:
                row = conn.execute(
                    "SELECT * FROM users WHERE username = ?", (username.strip(),)
                ).fetchone()
            if row is None or row["password"] != hash_password(password):
                return False, "Invalid username or password.", None
            return True, "Login successful.", dict(row)
        except sqlite3.Error as e:
            return False, str(e), None

    def get_profile(self, user_id: int) -> Optional[dict]:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, username, email, role, bio, created_at
                FROM users WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def post_count(self, user_id: int) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM posts WHERE author_id = ?", (user_id,)
            ).fetchone()
        return int(row["c"]) if row else 0

    def all_users(self) -> List[sqlite3.Row]:
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT id, username, email, role, created_at FROM users ORDER BY id"
            ).fetchall()

    def delete_user(self, user_id: int) -> Tuple[bool, str]:
        try:
            with self.db.connect() as conn:
                cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
                if cur.rowcount == 0:
                    return False, "User not found."
            return True, "User deleted."
        except sqlite3.Error as e:
            return False, str(e)


class PostService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(
        self, title: str, content: str, author_id: int, category: str, tags: str
    ) -> Tuple[bool, str]:
        if not title.strip():
            return False, "Title cannot be empty."
        if not content.strip():
            return False, "Content cannot be empty."
        try:
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO posts (title, content, author_id, category, tags, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        title.strip(),
                        content.strip(),
                        author_id,
                        category.strip() or "General",
                        tags.strip(),
                        now_str(),
                    ),
                )
            return True, "Post created."
        except sqlite3.Error as e:
            return False, str(e)

    def get(self, post_id: int) -> Optional[sqlite3.Row]:
        with self.db.connect() as conn:
            return conn.execute(
                """
                SELECT p.*, u.username AS author_name
                FROM posts p JOIN users u ON p.author_id = u.id
                WHERE p.id = ?
                """,
                (post_id,),
            ).fetchone()

    def update(
        self,
        post_id: int,
        title: str,
        content: str,
        category: str,
        tags: str,
        user_id: int,
        is_admin: bool,
    ) -> Tuple[bool, str]:
        post = self.get(post_id)
        if post is None:
            return False, "Invalid post ID."
        if not is_admin and post["author_id"] != user_id:
            return False, "You can only edit your own posts."
        if not title.strip() or not content.strip():
            return False, "Title and content cannot be empty."
        try:
            with self.db.connect() as conn:
                conn.execute(
                    """
                    UPDATE posts SET title=?, content=?, category=?, tags=? WHERE id=?
                    """,
                    (title.strip(), content.strip(), category.strip(), tags.strip(), post_id),
                )
            return True, "Post updated."
        except sqlite3.Error as e:
            return False, str(e)

    def delete(self, post_id: int, user_id: int, is_admin: bool) -> Tuple[bool, str]:
        post = self.get(post_id)
        if post is None:
            return False, "Invalid post ID."
        if not is_admin and post["author_id"] != user_id:
            return False, "You can only delete your own posts."
        try:
            with self.db.connect() as conn:
                conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            return True, "Post deleted."
        except sqlite3.Error as e:
            return False, str(e)

    def list_posts(
        self,
        search: str = "",
        category: str = "All",
        page: int = 1,
        per_page: int = POSTS_PER_PAGE,
        author_id: Optional[int] = None,
    ) -> Tuple[List[sqlite3.Row], int]:
        sql = """
            SELECT p.*, u.username AS author_name
            FROM posts p JOIN users u ON p.author_id = u.id
            WHERE 1=1
        """
        params: List[Any] = []
        if search.strip():
            sql += " AND (LOWER(p.title) LIKE LOWER(?) OR LOWER(p.content) LIKE LOWER(?) OR LOWER(p.tags) LIKE LOWER(?))"
            like = "%%%s%%" % search.strip()
            params.extend([like, like, like])
        if category and category != "All":
            sql += " AND LOWER(p.category) = LOWER(?)"
            params.append(category.strip())
        if author_id is not None:
            sql += " AND p.author_id = ?"
            params.append(author_id)
        sql += " ORDER BY p.created_at DESC"

        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        total = len(rows)
        start = max(0, (page - 1) * per_page)
        end = start + per_page
        return rows[start:end], total

    def categories(self) -> List[str]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT category FROM posts ORDER BY category COLLATE NOCASE"
            ).fetchall()
        return [r["category"] for r in rows]

    def vote(self, post_id: int, user_id: int, vote_type: str) -> Tuple[bool, str]:
        if vote_type not in ("like", "dislike"):
            return False, "Invalid vote."
        if self.get(post_id) is None:
            return False, "Post not found."
        try:
            with self.db.connect() as conn:
                old = conn.execute(
                    "SELECT vote_type FROM post_votes WHERE user_id=? AND post_id=?",
                    (user_id, post_id),
                ).fetchone()

                if old is None:
                    conn.execute(
                        "INSERT INTO post_votes (user_id, post_id, vote_type) VALUES (?,?,?)",
                        (user_id, post_id, vote_type),
                    )
                    col = "likes" if vote_type == "like" else "dislikes"
                    conn.execute(
                        "UPDATE posts SET %s = %s + 1 WHERE id=?" % (col, col),
                        (post_id,),
                    )
                    return True, "Vote recorded."

                if old["vote_type"] == vote_type:
                    conn.execute(
                        "DELETE FROM post_votes WHERE user_id=? AND post_id=?",
                        (user_id, post_id),
                    )
                    col = "likes" if vote_type == "like" else "dislikes"
                    conn.execute(
                        "UPDATE posts SET %s = MAX(0, %s - 1) WHERE id=?" % (col, col),
                        (post_id,),
                    )
                    return True, "Vote removed."

                conn.execute(
                    "UPDATE post_votes SET vote_type=? WHERE user_id=? AND post_id=?",
                    (vote_type, user_id, post_id),
                )
                if vote_type == "like":
                    conn.execute(
                        "UPDATE posts SET dislikes=MAX(0,dislikes-1), likes=likes+1 WHERE id=?",
                        (post_id,),
                    )
                else:
                    conn.execute(
                        "UPDATE posts SET likes=MAX(0,likes-1), dislikes=dislikes+1 WHERE id=?",
                        (post_id,),
                    )
                return True, "Vote updated."
        except sqlite3.Error as e:
            return False, str(e)


class CommentService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add(
        self, post_id: int, message: str, name: str, user_id: Optional[int]
    ) -> Tuple[bool, str]:
        if not message.strip():
            return False, "Comment cannot be empty."
        if not name.strip():
            return False, "Name is required."
        with self.db.connect() as conn:
            exists = conn.execute(
                "SELECT id FROM posts WHERE id=?", (post_id,)
            ).fetchone()
        if exists is None:
            return False, "Invalid post ID."
        try:
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO comments (post_id, user_id, commenter_name, message, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (post_id, user_id, name.strip(), message.strip(), now_str()),
                )
            return True, "Comment added."
        except sqlite3.Error as e:
            return False, str(e)

    def list_for_post(self, post_id: int) -> List[sqlite3.Row]:
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT * FROM comments WHERE post_id=? ORDER BY created_at ASC",
                (post_id,),
            ).fetchall()

    def all_comments(self) -> List[sqlite3.Row]:
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT id, post_id, commenter_name, message FROM comments ORDER BY id DESC"
            ).fetchall()

    def delete(self, comment_id: int) -> Tuple[bool, str]:
        try:
            with self.db.connect() as conn:
                cur = conn.execute("DELETE FROM comments WHERE id=?", (comment_id,))
                if cur.rowcount == 0:
                    return False, "Comment not found."
            return True, "Comment deleted."
        except sqlite3.Error as e:
            return False, str(e)


def export_pdf(path: str, post: sqlite3.Row, comments: List[sqlite3.Row]) -> Tuple[bool, str]:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        doc = SimpleDocTemplate(path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = [
            Paragraph("<b>%s</b>" % post["title"], styles["Title"]),
            Spacer(1, 12),
            Paragraph(
                "<i>By %s | %s | %s</i>"
                % (post["author_name"], post["category"], post["created_at"]),
                styles["Normal"],
            ),
            Spacer(1, 12),
            Paragraph(post["content"].replace("\n", "<br/>"), styles["Normal"]),
            Spacer(1, 16),
            Paragraph("<b>Comments</b>", styles["Heading2"]),
        ]
        if not comments:
            story.append(Paragraph("<i>No comments.</i>", styles["Normal"]))
        else:
            for c in comments:
                story.append(
                    Paragraph(
                        "<b>%s</b> (%s): %s"
                        % (c["commenter_name"], c["created_at"], c["message"]),
                        styles["Normal"],
                    )
                )
                story.append(Spacer(1, 6))
        doc.build(story)
        return True, "PDF saved: " + path
    except ImportError:
        return False, "Install reportlab: pip install reportlab"
    except Exception as e:
        return False, str(e)


def export_txt(path: str, post: sqlite3.Row, comments: List[sqlite3.Row]) -> None:
    lines = [
        "=" * 50,
        post["title"],
        "Author: %s | Category: %s" % (post["author_name"], post["category"]),
        "Tags: %s | Date: %s" % (post["tags"] or "-", post["created_at"]),
        "Likes: %d | Dislikes: %d" % (post["likes"], post["dislikes"]),
        "=" * 50,
        "",
        post["content"],
        "",
        "--- Comments ---",
    ]
    if not comments:
        lines.append("No comments.")
    else:
        for c in comments:
            lines.append("[%s] %s: %s" % (c["created_at"], c["commenter_name"], c["message"]))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# =============================================================================
# GUI
# =============================================================================
class BlogApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.db = Database()
        self.users = UserService(self.db)
        self.posts = PostService(self.db)
        self.comments = CommentService(self.db)
        self.session_user: Optional[dict] = None
        self.page = 1
        self.total_pages = 1
        self.my_posts_only = False
        self._setup_window()
        self._setup_styles()
        self.show_login()

    def _setup_window(self) -> None:
        self.root.title("Blog Management System")
        self.root.geometry("1100x700")
        self.root.minsize(900, 600)
        self.root.configure(bg=THEME["bg"])

    def _setup_styles(self) -> None:
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", background=THEME["bg"], foreground=THEME["text"])
        s.configure("TFrame", background=THEME["bg"])
        s.configure("Card.TFrame", background=THEME["card"])
        s.configure(
            "Title.TLabel",
            background=THEME["bg"],
            foreground=THEME["text"],
            font=("Segoe UI", 18, "bold"),
        )
        s.configure(
            "Header.TLabel",
            background=THEME["bg"],
            foreground=THEME["text"],
            font=("Segoe UI", 13, "bold"),
        )
        s.configure(
            "Muted.TLabel",
            background=THEME["card"],
            foreground=THEME["muted"],
            font=("Segoe UI", 10),
        )
        s.configure("TLabel", background=THEME["card"], foreground=THEME["text"])
        s.configure("TButton", font=("Segoe UI", 10), padding=8)
        s.configure(
            "Treeview",
            background=THEME["surface"],
            foreground=THEME["text"],
            fieldbackground=THEME["surface"],
            rowheight=26,
        )
        s.configure(
            "Treeview.Heading",
            background=THEME["card"],
            foreground=THEME["text"],
            font=("Segoe UI", 10, "bold"),
        )
        s.map("Treeview", background=[("selected", THEME["accent"])])
        s.configure("TNotebook", background=THEME["bg"], borderwidth=0)
        s.configure(
            "TNotebook.Tab",
            background=THEME["card"],
            foreground=THEME["muted"],
            padding=(12, 8),
        )
        s.map(
            "TNotebook.Tab",
            background=[("selected", THEME["surface"])],
            foreground=[("selected", THEME["text"])],
        )
        s.configure("TEntry", fieldbackground=THEME["input"], foreground=THEME["text"])
        s.configure("TCombobox", fieldbackground=THEME["input"], foreground=THEME["text"])

    @property
    def logged_in(self) -> bool:
        return self.session_user is not None

    @property
    def is_admin(self) -> bool:
        return self.logged_in and self.session_user.get("role") == "Admin"

    @property
    def uid(self) -> int:
        return int(self.session_user["id"])

    def _clear(self) -> None:
        for w in self.root.winfo_children():
            w.destroy()

    def _card(self, parent: tk.Widget, title: str) -> ttk.Frame:
        outer = tk.Frame(
            parent,
            bg=THEME["card"],
            highlightbackground=THEME["border"],
            highlightthickness=1,
        )
        outer.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        inner = ttk.Frame(outer, style="Card.TFrame", padding=16)
        inner.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            inner,
            text=title,
            font=("Segoe UI", 12, "bold"),
            background=THEME["card"],
            foreground=THEME["text"],
        ).pack(anchor="w", pady=(0, 10))
        return inner

    def _form_row(self, parent: ttk.Frame, label: str, width: int = 32) -> tk.StringVar:
        var = tk.StringVar()
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text=label, width=14).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=var, width=width).pack(side=tk.LEFT, fill=tk.X)
        return var

    def _text_box(self, parent: ttk.Frame, label: str, height: int = 10) -> tk.Text:
        ttk.Label(parent, text=label, background=THEME["card"]).pack(anchor="w", pady=(6, 2))
        box = tk.Text(
            parent,
            height=height,
            bg=THEME["input"],
            fg=THEME["text"],
            insertbackground=THEME["text"],
            relief=tk.FLAT,
            font=("Segoe UI", 10),
            wrap=tk.WORD,
        )
        box.pack(fill=tk.BOTH, expand=True, pady=4)
        return box

    # ----- Auth -----
    def show_login(self) -> None:
        self._clear()
        self.root.bind("<Return>", self._on_login_enter)

        wrap = ttk.Frame(self.root, padding=50)
        wrap.pack(expand=True)
        ttk.Label(wrap, text="Blog Management System", style="Title.TLabel").pack()
        ttk.Label(wrap, text="Posts • Users • Comments", style="Title.TLabel").pack(pady=(0, 20))

        box = tk.Frame(wrap, bg=THEME["card"], highlightbackground=THEME["border"], highlightthickness=1)
        box.pack()
        inner = ttk.Frame(box, style="Card.TFrame", padding=28)
        inner.pack()

        self.login_user = self._form_row(inner, "Username")
        self.login_pass = self._form_row(inner, "Password")
        self.login_pass_entry = None
        for child in inner.winfo_children():
            if isinstance(child, ttk.Frame):
                for w in child.winfo_children():
                    if isinstance(w, ttk.Entry) and w.cget("textvariable") == str(self.login_pass):
                        w.configure(show="*")

        btns = ttk.Frame(inner, style="Card.TFrame")
        btns.pack(fill=tk.X, pady=(14, 0))
        ttk.Button(btns, text="Login", command=self.do_login).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btns, text="Register", command=self.show_register).pack(side=tk.LEFT)
        ttk.Label(inner, text="Admin: admin / Admin@123", style="Muted.TLabel").pack(pady=(12, 0))

    def _on_login_enter(self, _event=None) -> None:
        self.do_login()

    def show_register(self) -> None:
        self._clear()
        self.root.unbind("<Return>")

        wrap = ttk.Frame(self.root, padding=30)
        wrap.pack(fill=tk.BOTH, expand=True)
        card = self._card(wrap, "Register")

        self.reg_user = self._form_row(card, "Username *")
        self.reg_email = self._form_row(card, "Email *")
        self.reg_pass = self._form_row(card, "Password *")
        self.reg_bio = self._form_row(card, "Bio")

        ttk.Button(card, text="Create Account", command=self.do_register).pack(anchor="w", pady=12)
        ttk.Button(card, text="Back to Login", command=self.show_login).pack(anchor="w")

    def do_login(self) -> None:
        ok, msg, user = self.users.login(self.login_user.get(), self.login_pass.get())
        if ok and user:
            self.session_user = user
            self.page = 1
            self.my_posts_only = False
            self.root.unbind("<Return>")
            self.show_main()
        else:
            messagebox.showerror("Login", msg)

    def do_register(self) -> None:
        ok, msg = self.users.register(
            self.reg_user.get(),
            self.reg_email.get(),
            self.reg_pass.get(),
            self.reg_bio.get(),
        )
        if ok:
            messagebox.showinfo("Register", msg)
            self.show_login()
        else:
            messagebox.showerror("Register", msg)

    def do_logout(self) -> None:
        self.session_user = None
        self.show_login()

    def show_profile(self) -> None:
        p = self.users.get_profile(self.uid)
        if not p:
            messagebox.showerror("Profile", "User not found.")
            return
        messagebox.showinfo(
            "My Profile",
            "Username: %s\nEmail: %s\nRole: %s\nBio: %s\nJoined: %s\nPosts: %d"
            % (
                p["username"],
                p["email"],
                p["role"],
                p["bio"] or "-",
                p["created_at"],
                self.users.post_count(self.uid),
            ),
        )

    # ----- Main -----
    def show_main(self) -> None:
        self._clear()

        top = ttk.Frame(self.root, padding=(16, 12))
        top.pack(fill=tk.X)
        ttk.Label(
            top,
            text="Hello, %s (%s)" % (self.session_user["username"], self.session_user["role"]),
            style="Header.TLabel",
        ).pack(side=tk.LEFT)
        ttk.Button(top, text="Profile", command=self.show_profile).pack(side=tk.RIGHT, padx=4)
        ttk.Button(top, text="Logout", command=self.do_logout).pack(side=tk.RIGHT)

        nb = ttk.Notebook(self.root, padding=8)
        nb.pack(fill=tk.BOTH, expand=True)

        self.tab_view = ttk.Frame(nb)
        self.tab_create = ttk.Frame(nb)
        self.tab_edit = ttk.Frame(nb)
        self.tab_comments = ttk.Frame(nb)

        nb.add(self.tab_view, text="View Posts")
        nb.add(self.tab_create, text="Create Post")
        nb.add(self.tab_edit, text="Edit / Delete")
        nb.add(self.tab_comments, text="Comments")

        if self.is_admin:
            self.tab_admin = ttk.Frame(nb)
            nb.add(self.tab_admin, text="Admin Panel")

        self.build_view_tab()
        self.build_create_tab()
        self.build_edit_tab()
        self.build_comments_tab()
        if self.is_admin:
            self.build_admin_tab()

    # ----- View posts -----
    def build_view_tab(self) -> None:
        card = self._card(self.tab_view, "All Posts")

        bar = ttk.Frame(card, style="Card.TFrame")
        bar.pack(fill=tk.X, pady=(0, 8))
        self.search_var = tk.StringVar()
        self.cat_var = tk.StringVar(value="All")

        ttk.Label(bar, text="Search:").pack(side=tk.LEFT)
        ent = ttk.Entry(bar, textvariable=self.search_var, width=22)
        ent.pack(side=tk.LEFT, padx=6)
        ent.bind("<KeyRelease>", lambda _e: self.refresh_posts())

        ttk.Label(bar, text="Category:").pack(side=tk.LEFT, padx=(8, 0))
        self.cat_combo = ttk.Combobox(
            bar, textvariable=self.cat_var, width=14, state="readonly"
        )
        self.cat_combo.pack(side=tk.LEFT, padx=6)
        self.cat_combo.bind("<<ComboboxSelected>>", lambda _e: self.go_page(1))

        ttk.Button(bar, text="Search", command=lambda: self.go_page(1)).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="My Posts", command=self.toggle_my_posts).pack(side=tk.LEFT, padx=4)

        cols = ("id", "title", "author", "category", "likes", "dislikes", "date")
        self.tree = ttk.Treeview(card, columns=cols, show="headings", height=14)
        for c, w in zip(cols, (45, 200, 90, 90, 50, 60, 130)):
            self.tree.heading(c, text=c.title())
            self.tree.column(c, width=w)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        pag = ttk.Frame(card, style="Card.TFrame")
        pag.pack(fill=tk.X, pady=8)
        self.page_lbl = ttk.Label(pag, text="Page 1/1")
        self.page_lbl.pack(side=tk.LEFT)
        ttk.Button(pag, text="Prev", command=self.prev_page).pack(side=tk.LEFT, padx=8)
        ttk.Button(pag, text="Next", command=self.next_page).pack(side=tk.LEFT)

        act = ttk.Frame(card, style="Card.TFrame")
        act.pack(fill=tk.X)
        ttk.Button(act, text="View Post", command=self.view_post).pack(side=tk.LEFT, padx=4)
        ttk.Button(act, text="Like", command=lambda: self.do_vote("like")).pack(side=tk.LEFT, padx=4)
        ttk.Button(act, text="Dislike", command=lambda: self.do_vote("dislike")).pack(side=tk.LEFT, padx=4)
        ttk.Button(act, text="Export PDF", command=self.do_export_pdf).pack(side=tk.LEFT, padx=4)
        ttk.Button(act, text="Export TXT", command=self.do_export_txt).pack(side=tk.LEFT, padx=4)

        self.refresh_posts()

    def selected_post_id(self) -> Optional[int]:
        sel = self.tree.selection()
        if not sel:
            return None
        try:
            return int(sel[0])
        except ValueError:
            return None

    def _on_select(self, _e=None) -> None:
        pass

    def go_page(self, page: int) -> None:
        self.page = max(1, page)
        self.refresh_posts()

    def prev_page(self) -> None:
        if self.page > 1:
            self.go_page(self.page - 1)

    def next_page(self) -> None:
        if self.page < self.total_pages:
            self.go_page(self.page + 1)

    def toggle_my_posts(self) -> None:
        self.my_posts_only = not self.my_posts_only
        self.go_page(1)

    def refresh_posts(self) -> None:
        if not hasattr(self, "tree"):
            return
        for i in self.tree.get_children():
            self.tree.delete(i)

        author = self.uid if self.my_posts_only else None
        rows, total = self.posts.list_posts(
            self.search_var.get(),
            self.cat_var.get(),
            self.page,
            POSTS_PER_PAGE,
            author,
        )
        self.total_pages = max(1, (total + POSTS_PER_PAGE - 1) // POSTS_PER_PAGE)
        if self.page > self.total_pages:
            self.page = self.total_pages

        cats = ["All"] + self.posts.categories()
        self.cat_combo["values"] = cats

        for p in rows:
            self.tree.insert(
                "",
                tk.END,
                iid=str(p["id"]),
                values=(
                    p["id"],
                    (p["title"][:38] + "..") if len(p["title"]) > 40 else p["title"],
                    p["author_name"],
                    p["category"],
                    p["likes"],
                    p["dislikes"],
                    p["created_at"],
                ),
            )
        self.page_lbl.config(
            text="Page %d/%d (%d posts)" % (self.page, self.total_pages, total)
        )

    def view_post(self) -> None:
        pid = self.selected_post_id()
        if pid is None:
            messagebox.showwarning("View", "Select a post.")
            return
        post = self.posts.get(pid)
        if post is None:
            messagebox.showerror("View", "Invalid post ID.")
            return
        win = tk.Toplevel(self.root)
        win.title(post["title"])
        win.geometry("620x480")
        win.configure(bg=THEME["surface"])
        txt = tk.Text(
            win,
            bg=THEME["surface"],
            fg=THEME["text"],
            font=("Segoe UI", 11),
            wrap=tk.WORD,
            padx=16,
            pady=16,
        )
        txt.pack(fill=tk.BOTH, expand=True)
        body = (
            "%s\n%s\n\nBy %s | %s | %s\nTags: %s\nLikes: %d  Dislikes: %d\n\n%s"
            % (
                post["title"],
                "-" * 40,
                post["author_name"],
                post["category"],
                post["created_at"],
                post["tags"] or "-",
                post["likes"],
                post["dislikes"],
                post["content"],
            )
        )
        txt.insert("1.0", body)
        txt.config(state=tk.DISABLED)

    def do_vote(self, vtype: str) -> None:
        pid = self.selected_post_id()
        if pid is None:
            messagebox.showwarning("Vote", "Select a post.")
            return
        ok, msg = self.posts.vote(pid, self.uid, vtype)
        if ok:
            self.refresh_posts()
        else:
            messagebox.showerror("Vote", msg)

    def do_export_pdf(self) -> None:
        pid = self.selected_post_id()
        if pid is None:
            messagebox.showwarning("Export", "Select a post.")
            return
        post = self.posts.get(pid)
        if post is None:
            return
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if path:
            ok, msg = export_pdf(path, post, self.comments.list_for_post(pid))
            if ok:
                messagebox.showinfo("Export", msg)
            else:
                messagebox.showerror("Export", msg)

    def do_export_txt(self) -> None:
        pid = self.selected_post_id()
        if pid is None:
            messagebox.showwarning("Export", "Select a post.")
            return
        post = self.posts.get(pid)
        if post is None:
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if path:
            export_txt(path, post, self.comments.list_for_post(pid))
            messagebox.showinfo("Export", "Saved: " + path)

    # ----- Create -----
    def build_create_tab(self) -> None:
        card = self._card(self.tab_create, "Create Post")
        self.new_title = self._form_row(card, "Title *")
        self.new_cat = self._form_row(card, "Category")
        self.new_tags = self._form_row(card, "Tags")
        self.new_content = self._text_box(card, "Content *", 12)
        ttk.Button(card, text="Publish Post", command=self.do_create).pack(anchor="w", pady=8)

    def do_create(self) -> None:
        content = self.new_content.get("1.0", tk.END).strip()
        ok, msg = self.posts.create(
            self.new_title.get(),
            content,
            self.uid,
            self.new_cat.get(),
            self.new_tags.get(),
        )
        if ok:
            messagebox.showinfo("Success", msg)
            self.new_title.set("")
            self.new_cat.set("")
            self.new_tags.set("")
            self.new_content.delete("1.0", tk.END)
            self.refresh_posts()
        else:
            messagebox.showerror("Error", msg)

    # ----- Edit / Delete -----
    def build_edit_tab(self) -> None:
        card = self._card(self.tab_edit, "Edit or Delete Post")
        self.edit_id = self._form_row(card, "Post ID *")
        ttk.Button(card, text="Load Post", command=self.load_for_edit).pack(anchor="w", pady=6)
        self.edit_title = self._form_row(card, "Title")
        self.edit_cat = self._form_row(card, "Category")
        self.edit_tags = self._form_row(card, "Tags")
        self.edit_content = self._text_box(card, "Content", 10)
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill=tk.X, pady=8)
        ttk.Button(row, text="Save", command=self.do_update).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(row, text="Delete", command=self.do_delete).pack(side=tk.LEFT)

    def load_for_edit(self) -> None:
        try:
            pid = int(self.edit_id.get().strip())
        except ValueError:
            messagebox.showwarning("Edit", "Enter a valid numeric Post ID.")
            return
        post = self.posts.get(pid)
        if post is None:
            messagebox.showerror("Edit", "Invalid post ID.")
            return
        if not self.is_admin and post["author_id"] != self.uid:
            messagebox.showerror("Edit", "You can only edit your own posts.")
            return
        self.edit_title.set(post["title"])
        self.edit_cat.set(post["category"])
        self.edit_tags.set(post["tags"] or "")
        self.edit_content.delete("1.0", tk.END)
        self.edit_content.insert("1.0", post["content"])

    def do_update(self) -> None:
        try:
            pid = int(self.edit_id.get().strip())
        except ValueError:
            messagebox.showwarning("Edit", "Enter a valid Post ID.")
            return
        ok, msg = self.posts.update(
            pid,
            self.edit_title.get(),
            self.edit_content.get("1.0", tk.END).strip(),
            self.edit_cat.get(),
            self.edit_tags.get(),
            self.uid,
            self.is_admin,
        )
        if ok:
            messagebox.showinfo("Success", msg)
            self.refresh_posts()
        else:
            messagebox.showerror("Error", msg)

    def do_delete(self) -> None:
        try:
            pid = int(self.edit_id.get().strip())
        except ValueError:
            messagebox.showwarning("Delete", "Enter a valid Post ID.")
            return
        if not messagebox.askyesno("Confirm", "Delete this post and all comments?"):
            return
        ok, msg = self.posts.delete(pid, self.uid, self.is_admin)
        if ok:
            messagebox.showinfo("Deleted", msg)
            self.refresh_posts()
            if self.is_admin:
                self.refresh_admin()
        else:
            messagebox.showerror("Error", msg)

    # ----- Comments -----
    def build_comments_tab(self) -> None:
        card = self._card(self.tab_comments, "Post Comments")
        self.cmt_post_id = self._form_row(card, "Post ID *")
        ttk.Button(card, text="Load Comments", command=self.load_comments).pack(anchor="w", pady=6)
        self.cmt_display = tk.Text(
            card,
            height=10,
            bg=THEME["surface"],
            fg=THEME["text"],
            font=("Consolas", 10),
            relief=tk.FLAT,
            state=tk.DISABLED,
        )
        self.cmt_display.pack(fill=tk.BOTH, expand=True, pady=6)
        self.cmt_msg = self._form_row(card, "Your Comment *")
        ttk.Button(card, text="Add Comment", command=self.do_add_comment).pack(anchor="w", pady=6)

    def load_comments(self) -> None:
        try:
            pid = int(self.cmt_post_id.get().strip())
        except ValueError:
            messagebox.showwarning("Comments", "Enter a valid Post ID.")
            return
        post = self.posts.get(pid)
        if post is None:
            messagebox.showerror("Comments", "Invalid post ID.")
            return
        rows = self.comments.list_for_post(pid)
        self.cmt_display.config(state=tk.NORMAL)
        self.cmt_display.delete("1.0", tk.END)
        self.cmt_display.insert(tk.END, "Post: %s\n%s\n" % (post["title"], "-" * 40))
        if not rows:
            self.cmt_display.insert(tk.END, "No comments yet.\n")
        else:
            for c in rows:
                self.cmt_display.insert(
                    tk.END,
                    "[%s] %s:\n  %s\n\n" % (c["created_at"], c["commenter_name"], c["message"]),
                )
        self.cmt_display.config(state=tk.DISABLED)

    def do_add_comment(self) -> None:
        try:
            pid = int(self.cmt_post_id.get().strip())
        except ValueError:
            messagebox.showwarning("Comment", "Enter a valid Post ID.")
            return
        ok, msg = self.comments.add(
            pid,
            self.cmt_msg.get(),
            self.session_user["username"],
            self.uid,
        )
        if ok:
            messagebox.showinfo("Success", msg)
            self.cmt_msg.set("")
            self.load_comments()
        else:
            messagebox.showerror("Error", msg)

    # ----- Admin -----
    def build_admin_tab(self) -> None:
        card = self._card(self.tab_admin, "Admin Panel")
        nb = ttk.Notebook(card)
        nb.pack(fill=tk.BOTH, expand=True)

        f_users = ttk.Frame(nb)
        f_posts = ttk.Frame(nb)
        f_cmt = ttk.Frame(nb)
        nb.add(f_users, text="Users")
        nb.add(f_posts, text="Posts")
        nb.add(f_cmt, text="Comments")

        self.adm_users = ttk.Treeview(
            f_users, columns=("id", "user", "email", "role"), show="headings", height=8
        )
        for c, w in zip(("id", "user", "email", "role"), (40, 120, 180, 80)):
            self.adm_users.heading(c, text=c.title())
            self.adm_users.column(c, width=w)
        self.adm_users.pack(fill=tk.BOTH, expand=True, pady=6)
        ttk.Button(f_users, text="Delete User", command=self.admin_del_user).pack(anchor="w")

        self.adm_posts = ttk.Treeview(
            f_posts, columns=("id", "title", "author"), show="headings", height=8
        )
        for c, w in zip(("id", "title", "author"), (40, 220, 120)):
            self.adm_posts.heading(c, text=c.title())
            self.adm_posts.column(c, width=w)
        self.adm_posts.pack(fill=tk.BOTH, expand=True, pady=6)
        ttk.Button(f_posts, text="Delete Post", command=self.admin_del_post).pack(anchor="w")

        self.adm_cmt = ttk.Treeview(
            f_cmt, columns=("id", "post", "name", "msg"), show="headings", height=8
        )
        for c, w in zip(("id", "post", "name", "msg"), (40, 60, 100, 220)):
            self.adm_cmt.heading(c, text=c.title())
            self.adm_cmt.column(c, width=w)
        self.adm_cmt.pack(fill=tk.BOTH, expand=True, pady=6)
        ttk.Button(f_cmt, text="Delete Comment", command=self.admin_del_cmt).pack(anchor="w")

        self.refresh_admin()

    def refresh_admin(self) -> None:
        if not self.is_admin or not hasattr(self, "adm_users"):
            return
        for tree in (self.adm_users, self.adm_posts, self.adm_cmt):
            for i in tree.get_children():
                tree.delete(i)
        for u in self.users.all_users():
            self.adm_users.insert(
                "", tk.END, iid=str(u["id"]),
                values=(u["id"], u["username"], u["email"], u["role"]),
            )
        rows, _ = self.posts.list_posts(per_page=10000)
        for p in rows:
            self.adm_posts.insert(
                "", tk.END, iid=str(p["id"]),
                values=(p["id"], p["title"][:35], p["author_name"]),
            )
        for c in self.comments.all_comments():
            self.adm_cmt.insert(
                "", tk.END, iid=str(c["id"]),
                values=(c["id"], c["post_id"], c["commenter_name"], c["message"][:40]),
            )

    def admin_del_user(self) -> None:
        sel = self.adm_users.selection()
        if not sel:
            messagebox.showwarning("Admin", "Select a user.")
            return
        uid = int(sel[0])
        if uid == self.uid:
            messagebox.showwarning("Admin", "Cannot delete yourself.")
            return
        if messagebox.askyesno("Confirm", "Delete this user and all their posts?"):
            ok, msg = self.users.delete_user(uid)
            if ok:
                messagebox.showinfo("Admin", msg)
                self.refresh_admin()
                self.refresh_posts()
            else:
                messagebox.showerror("Admin", msg)

    def admin_del_post(self) -> None:
        sel = self.adm_posts.selection()
        if not sel:
            messagebox.showwarning("Admin", "Select a post.")
            return
        if messagebox.askyesno("Confirm", "Delete this post?"):
            ok, msg = self.posts.delete(int(sel[0]), self.uid, True)
            if ok:
                messagebox.showinfo("Admin", msg)
                self.refresh_admin()
                self.refresh_posts()
            else:
                messagebox.showerror("Admin", msg)

    def admin_del_cmt(self) -> None:
        sel = self.adm_cmt.selection()
        if not sel:
            messagebox.showwarning("Admin", "Select a comment.")
            return
        if messagebox.askyesno("Confirm", "Delete this comment?"):
            ok, msg = self.comments.delete(int(sel[0]))
            if ok:
                messagebox.showinfo("Admin", msg)
                self.refresh_admin()
            else:
                messagebox.showerror("Admin", msg)


def main() -> None:
    root = tk.Tk()
    try:
        BlogApp(root)
        root.mainloop()
    except Exception as exc:
        messagebox.showerror("Fatal Error", str(exc))


if __name__ == "__main__":
    main()