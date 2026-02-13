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
    "hi-IN": "Namaste, welcome to Jadau.",
    "en-IN": "Namaste, welcome to Jadau.",
}


# Default IVR prompts (English only) used by the voice IVR.
# These can be overridden via the admin console.
DEFAULT_IVR_PROMPTS = {
    # Main menu - intent selection
    "menu": "Please choose one of the following options: General Inquiry, Try Near You, or Price Request.",
    "reprompt": "I did not catch your response. Please say General Inquiry, Try Near You, or Price Request.",
    "invalid": "Sorry, I didn't understand that. Please try again.",
    
    # Name collection - asked after intent selection
    "name_prompt": "May I have your name please, so that we can provide you with more specific assistance?",
    
    # After General Inquiry or Try Near You - product or category
    "assist_type_prompt": "Would you like assistance with a specific product or a product category?",
    
    # Product ID collection
    "product_id_prompt": "Please provide the Product ID for the item you're referring to.",
    
    # Category name collection  
    "category_prompt": "Kindly mention the category name you're looking for.",
    
    # Price request - ask for product ID
    "price_product_prompt": "Please provide the Product ID so I can check the pricing details for you.",
    
    # Confirmation before connecting to agent
    "confirmation": "Thank you. While I connect you to our agent for further assistance, please briefly describe your query.",
    
    # Connection announcement
    "connecting": "Please wait while we connect you to our expert.",
    
    # Default fallback message when no agent available
    "no_agent": "Sorry, we cannot connect your call right now. Please try again later.",
}
