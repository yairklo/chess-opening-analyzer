"""Hebrew names for the common openings (Lichess names are English). Anything not listed stays in English."""
import re

# family -> (full Hebrew name, short form used in front of a variation)
FAMILIES = {
    "Italian Game": ("פתיחה איטלקית", "איטלקית"),
    "Sicilian Defense": ("הגנה סיציליאנית", "סיציליאנית"),
    "French Defense": ("הגנה צרפתית", "צרפתית"),
    "Caro-Kann Defense": ("הגנת קארו־קאן", "קארו־קאן"),
    "Ruy Lopez": ("רוי לופז", "רוי לופז"),
    "Queen's Gambit": ("גמביט המלכה", "גמביט המלכה"),
    "Queen's Gambit Declined": ("גמביט המלכה מסורב", "גמביט המלכה מסורב"),
    "Queen's Gambit Accepted": ("גמביט המלכה מקובל", "גמביט המלכה מקובל"),
    "Queen's Pawn Game": ("פתיחת פיון המלכה", "פיון המלכה"),
    "King's Pawn Game": ("פתיחת פיון המלך", "פיון המלך"),
    "King's Gambit": ("גמביט המלך", "גמביט המלך"),
    "Pirc Defense": ("הגנת פירץ", "פירץ"),
    "Scandinavian Defense": ("הגנה סקנדינבית", "סקנדינבית"),
    "Vienna Game": ("פתיחת וינה", "וינה"),
    "Bishop's Opening": ("פתיחת הרץ", "פתיחת הרץ"),
    "Scotch Game": ("פתיחה סקוטית", "סקוטית"),
    "Russian Game": ("הגנה רוסית", "רוסית"),
    "Alekhine Defense": ("הגנת אלכין", "אלכין"),
    "Modern Defense": ("הגנה מודרנית", "מודרנית"),
    "Philidor Defense": ("הגנת פילידור", "פילידור"),
    "Dutch Defense": ("הגנה הולנדית", "הולנדית"),
    "Slav Defense": ("הגנה סלאבית", "סלאבית"),
    "English Opening": ("פתיחה אנגלית", "אנגלית"),
    "London System": ("שיטת לונדון", "לונדון"),
    "Indian Defense": ("הגנה הודית", "הודית"),
    "King's Indian Defense": ("הגנה הודית המלך", "הודית המלך"),
    "Queen's Indian Defense": ("הגנה הודית המלכה", "הודית המלכה"),
    "Nimzo-Indian Defense": ("הגנה נימצוביץ'־הודית", "נימצוביץ'־הודית"),
    "Catalan Opening": ("פתיחה קטלאנית", "קטלאנית"),
    "Zukertort Opening": ("פתיחת צוקרטורט", "צוקרטורט"),
    "Réti Opening": ("פתיחת רטי", "רטי"),
    "Four Knights Game": ("משחק ארבעת הפרשים", "ארבעת הפרשים"),
    "Evans Gambit": ("גמביט אוואנס", "גמביט אוואנס"),
    "Danish Gambit": ("גמביט דני", "גמביט דני"),
    "Hungarian Opening": ("פתיחה הונגרית", "הונגרית"),
    "Polish Opening": ("פתיחה פולנית", "פולנית"),
    "Trompowsky Attack": ("התקפת טרומפובסקי", "טרומפובסקי"),
}

# variations that read well on their own or after a family's short name
VARIATIONS = {
    "Classical Variation": "קלאסית", "Classical": "קלאסית", "Advance Variation": "מתקדמת",
    "Exchange Variation": "חילופים", "Giuoco Piano": "ג'וקו פיאנו", "Two Knights Defense": "הגנת שני הפרשים",
    "Rousseau Gambit": "גמביט רוסו", "Vienna Gambit": "גמביט וינה", "Max Lange Defense": "הגנת מקס לנגה",
    "Evans Gambit": "גמביט אוואנס", "Fried Liver Attack": "התקפת הכבד המטוגן", "Scotch Gambit": "גמביט סקוטי",
    "Berlin Defense": "הגנת ברלין", "Marshall Attack": "התקפת מרשל", "Najdorf Variation": "נאג'דורף",
    "Dragon Variation": "דרקון", "Alapin Variation": "אלאפין", "Smith-Morra Gambit": "גמביט סמית'־מורה",
    "Latvian Gambit": "גמביט לטבי", "Blackmar-Diemer Gambit": "גמביט בלקמר־דימר", "Stonewall Attack": "התקפת סטונוול",
    "Tarrasch Variation": "טראש", "Winawer Variation": "וינאבר", "Panov Attack": "התקפת פאנוב",
    "Hippopotamus": "היפופוטם", "Sämisch Variation": "זמיש", "Fianchetto Variation": "פיאנקטו",
}

_TRIM = re.compile(r"\s+(Variation|Defense|Game|Opening|Attack)$")


def split_name(name):
    family, _, var = name.partition(":")
    return family.strip(), var.split(",")[0].strip()


def he_title(name):
    """Hebrew title for an English opening name; the English name itself when nothing is known."""
    family, var = split_name(name)
    full, short = FAMILIES.get(family, (None, None))
    if var in VARIATIONS:
        v = VARIATIONS[var]
        return v if var.endswith(("Gambit", "Defense", "Attack")) or short is None else f"{short} {v}"
    if full:
        return full
    return VARIATIONS.get(family, name)


def en_sub(name, color_label=""):
    """'Caro-Kann · Classical · לבן': the English name, shortened, with the colour."""
    family, var = split_name(name)
    parts = [_TRIM.sub("", family) if var else family]
    if var:
        parts.append(_TRIM.sub("", var) if not var.endswith(("Gambit", "Defense", "Attack")) else var)
    if color_label:
        parts.append(color_label)
    return " · ".join(parts)
