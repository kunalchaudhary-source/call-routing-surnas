"""Default data for initializing the database."""

DEFAULT_CORRECTIONS = {
    # Map common STT mishearings to the six canonical categories used by the IVR
    # Necklaces
    "neck lace": "necklace",
    "neckless": "necklace",
    "nekless": "necklace",
    "neklace": "necklace",
    "neckelace": "necklace",
    "necklaces": "necklace",
    "haar": "necklace",

    # Bangles
    "bangle": "bangles",
    "bangles": "bangles",
    "kada": "bangles",
    "kadan": "bangles",

    # Bracelets
    "bracelet": "bracelets",
    "braclet": "bracelets",
    "braclets": "bracelets",
    "bracelets": "bracelets",

    # Earrings
    "earring": "earrings",
    "earrings": "earrings",
    "jhumka": "earrings",
    "jhumkas": "earrings",
    "chandbali": "earrings",

    # Curated combinations (sets / combos)
    "curated combo": "curated combination",
    "curated combinations": "curated combination",
    "curation combination": "curated combination",
    "combo": "curated combination",
    "combination": "curated combination",
    "set": "curated combination",

    # Accessories
    "accessory": "accessories",
    "accessories": "accessories",
    "maang tikka": "accessories",
    "maangtikka": "accessories",
    "mang tikka": "accessories",
    "kamarband": "accessories",
    "waistband": "accessories",

}


DEFAULT_GREETINGS = {
    # Unified greeting for both Hindi and English per request
    "hi-IN": "noneed to diffrent type of greeting meessages",
    "en-IN": "noneed to diffrent type of greeting meessages",
}


# Default IVR prompts (English only) used by the voice IVR.
# These can be overridden via the admin console.
DEFAULT_IVR_PROMPTS = {
    "menu": "Please say the category you need help with — for example necklace, bangles, bracelets, earrings, curated combination, or accessories.",
    "reprompt": "I did not catch a valid choice. Please say a category name like necklace or earrings.",
    "confirmation": "Connecting you with a {{category}} expert now.",
    "invalid": "Sorry, that option is not available. Please choose again.",
}
