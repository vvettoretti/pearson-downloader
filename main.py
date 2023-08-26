from PearsonLib import Pearson

print("Pearson downloader by @vvettoretti")


username = input("Username: ")
password = input("Password: ")
pearson = Pearson(username=username, password=password)
if not pearson.login():
    print("Login failed.")


# Get and display the list of books
books = pearson.get_bookshelf()
if not books:
    print("No books available.")
else:
    print("Available books:")
    for idx, book in enumerate(books):
        print(f"[{idx}] {book['book_title']}")

    # Prompt user to choose a book
    while (book_choice := input("Choose a book (enter the corresponding number), or enter e to exit:")) != "e":
        book_choice = int(book_choice)
        if book_choice < 0 or book_choice >= len(books):
            print("Invalid choice.")

        else:
            chosen_book = books[book_choice]
            book_id = chosen_book.get("book_id")
            book_title = chosen_book.get("book_title")

            # Get user input for filename
            filename = input(f"Enter a filename for '{book_title}.pdf' (leave empty to use default): ")
            if not filename:
                filename = f"{book_title}.pdf"

            # Download the chosen book
            pearson.download_book(book_id, filename,show_progress=True)
            print("Book downloaded successfully!")
