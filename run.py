from MultipleFiles import create_app # Changed import statement
app = create_app()
if __name__ == "__main__":
    app.run(debug=True)
