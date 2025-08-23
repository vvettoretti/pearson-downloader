from PearsonLib import Pearson, PearsonError

print("Pearson downloader by @vvettoretti")

try:
    username = input("Username: ")
    password = input("Password: ")
    pearson = Pearson(username=username, password=password)
    
    if not pearson.login():
        print("Login failed.")
        exit(1)

    books = pearson.get_bookshelf()
    if not books:
        print("No books available.")
        exit(1)
        
    print("Available books:")
    for idx, book in enumerate(books):
        print(f"[{idx}] {book['book_title']}")

    while True:
        book_choice = input("Choose a book (number) or 'e' to exit: ")
        if book_choice.lower() == 'e':
            break
            
        try:
            book_choice = int(book_choice)
            if book_choice < 0 or book_choice >= len(books):
                print("Invalid choice.")
                continue
        except ValueError:
            print("Enter a valid number or 'e'.")
            continue

        chosen_book = books[book_choice]
        book_id = chosen_book.get("book_id")
        product_id = chosen_book.get("product_id")
        entitlement_source = chosen_book.get("entitlement_source", "PASSPORT")
        book_title = chosen_book.get("book_title")

        filename = input(f"Filename for '{book_title}' (empty for default): ").strip()
        if not filename:
            filename = book_title
        
        # Remove .pdf if user added it since we always save as PDF
        if not filename.endswith('.pdf'):
            filename = filename+".pdf"

      

        try:
            print("📚 Downloading...")
            saved_file = pearson.download_book(book_id, product_id, entitlement_source, filename, show_progress=True)
            print(f"✅ Saved: {saved_file}")
            
        except PearsonError as e:
            print(f"❌ Failed: {e}")
        except Exception as e:
            print(f"❌ Error: {e}")
            
except KeyboardInterrupt:
    print("\nCancelled.")
except PearsonError as e:
    print(f"❌ Error: {e}")
except Exception as e:
    print(f"❌ Error: {e}")
