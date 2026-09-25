from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import libsql_client
import os

app = FastAPI()

URL = os.environ.get("TURSO_DATABASE_URL")
TOKEN = os.environ.get("TURSO_AUTH_TOKEN")

def get_db():
    if not URL or not TOKEN:
        raise RuntimeError("Database credentials missing. Please add them in Vercel.")
    return libsql_client.create_client_sync(url=URL, auth_token=TOKEN)

def setup_database():
    client = get_db()
    client.execute('''
        CREATE TABLE IF NOT EXISTS books (
            book_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            isbn TEXT UNIQUE NOT NULL,
            published_year INTEGER,
            status TEXT DEFAULT 'Available'
        )
    ''')
    client.close()

# FIX 1: Safely trigger database setup only AFTER the server has fully booted
@app.on_event("startup")
def startup_event():
    if URL and TOKEN:
        setup_database()

class Book(BaseModel):
    title: str
    author: str
    isbn: str
    published_year: int

@app.get("/")
def read_root():
    return {"status": "Library API is live"}

@app.get("/books/search")
def search_books(q: str):
    client = get_db()
    search_pattern = f"%{q}%"
    result = client.execute('''
        SELECT * FROM books 
        WHERE title LIKE ? OR author LIKE ?
    ''', [search_pattern, search_pattern])
    
    # FIX 2: Fixed the missing list comprehension loop for 'row'
    records = [dict(zip(result.columns, row)) for row in result.rows]
    client.close()
    return records

@app.get("/books")
def get_books():
    client = get_db()
    result = client.execute('SELECT * FROM books')
    records = [dict(zip(result.columns, row)) for row in result.rows]
    client.close()
    return records

@app.post("/books")
def add_new_book(book: Book):
    client = get_db()
    try:
        client.execute('''
            INSERT INTO books (title, author, isbn, published_year)
            VALUES (?, ?, ?, ?)
        ''', [book.title, book.author, book.isbn, book.published_year])
        return {"status": "Success", "message": f"'{book.title}' added."}
    except Exception:
        raise HTTPException(status_code=400, detail="Book with this ISBN already exists.")
    finally:
        client.close()

@app.put("/books/{book_id}")
def update_book(book_id: int, book: Book):
    client = get_db()
    result = client.execute('''
        UPDATE books 
        SET title = ?, author = ?, isbn = ?, published_year = ?
        WHERE book_id = ?
    ''', [book.title, book.author, book.isbn, book.published_year, book_id])
    client.close()
    if result.rows_affected == 0:
        raise HTTPException(status_code=404, detail="Book not found")
    return {"status": "Success", "message": f"Book ID {book_id} updated."}

@app.delete("/books/{book_id}")
def delete_book(book_id: int):
    client = get_db()
    result = client.execute('DELETE FROM books WHERE book_id = ?', [book_id])
    client.close()
    if result.rows_affected == 0:
        raise HTTPException(status_code=404, detail="Book not found")
    return {"status": "Success", "message": f"Book ID {book_id} deleted."}

@app.patch("/books/{book_id}/checkout")
def checkout_book(book_id: int):
    client = get_db()
    result = client.execute('SELECT status FROM books WHERE book_id = ?', [book_id])
    if not result.rows:
        client.close()
        raise HTTPException(status_code=404, detail="Book not found")
    
    if result.rows[0][0] != 'Available':
        client.close()
        raise HTTPException(status_code=400, detail="Book is already checked out")
        
    client.execute('UPDATE books SET status = ? WHERE book_id = ?', ['Checked Out', book_id])
    client.close()
    return {"status": "Success", "message": f"Book ID {book_id} checked out."}

@app.patch("/books/{book_id}/return")
def return_book(book_id: int):
    client = get_db()
    result = client.execute('SELECT status FROM books WHERE book_id = ?', [book_id])
    if not result.rows:
        client.close()
        raise HTTPException(status_code=404, detail="Book not found")
    
    if result.rows[0][0] == 'Available':
        client.close()
        raise HTTPException(status_code=400, detail="Book is already in the library")
        
    client.execute('UPDATE books SET status = ? WHERE book_id = ?', ['Available', book_id])
    client.close()
    return {"status": "Success", "message": f"Book ID {book_id} returned."}
