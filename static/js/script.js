document.addEventListener("DOMContentLoaded", function() {
    var searchForm = document.getElementById("searchForm");
    var searchInput = document.getElementById("searchInput");

    searchForm.addEventListener("submit", function(event) {
        event.preventDefault();
        var query = searchInput.value;
        if (query) {
            window.location.href = "search.php?query=" + encodeURIComponent(query);
        }
    });
});
document.getElementById('loginIcon').addEventListener('click', function() {
    document.getElementById('authContainer').style.display = 'block';
});

document.getElementById('closeAuth').addEventListener('click', function() {
    document.getElementById('authContainer').style.display = 'none';
});
document.getElementById('loginIcon').addEventListener('click', function() {
    document.getElementById('authContainer').style.display

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>