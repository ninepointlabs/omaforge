.pragma library

function count(n) {
    if (!n) return ""
    if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e8 ? 0 : 1) + "M"
    if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e5 ? 0 : 1).replace(/\.0$/, "") + "k"
    return "" + n
}

function age(ts) {
    if (!ts) return ""
    var days = Math.floor((Date.now() / 1000 - ts) / 86400)
    if (days < 1) return "today"
    if (days < 2) return "yesterday"
    if (days < 60) return days + " days ago"
    if (days < 730) return Math.floor(days / 30) + " months ago"
    return Math.floor(days / 365) + " years ago"
}

// One line of the numbers each source actually has.
function stats(r) {
    var parts = []
    if (r.downloads) parts.push(count(r.downloads) + " downloads")
    if (r.downloads_monthly) parts.push(count(r.downloads_monthly) + " this month")
    if (r.favorites) parts.push(count(r.favorites) + (r.provider === "github" ? " stars" : " favorites"))
    if (r.updated) parts.push("updated " + age(r.updated))
    return parts.join("  ·  ")
}

var sorters = {
    "Relevance": null,
    "Most downloaded": function (a, b) { return b.downloads - a.downloads },
    "Most popular": function (a, b) {
        var ra = a.rank || 1e9, rb = b.rank || 1e9
        return ra !== rb ? ra - rb : b.downloads_monthly - a.downloads_monthly
    },
    "Most favorited": function (a, b) { return b.favorites - a.favorites },
    "Recently updated": function (a, b) { return b.updated - a.updated },
    "Name": function (a, b) { return a.name.toLowerCase() < b.name.toLowerCase() ? -1 : 1 }
}
