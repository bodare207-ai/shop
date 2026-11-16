from app import create_app

app = create_app()

if __name__ == "__main__":
    print("\n  ✅  Store:        http://localhost:5000")
    print("  ✅  Admin panel:  http://localhost:5000/admin\n")
    app.run(host="127.0.0.1", port=5000, debug=True)
