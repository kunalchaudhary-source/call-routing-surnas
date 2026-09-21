"""Default data for initializing greetings, prompts, and corrections in DB."""

DEFAULT_CORRECTIONS = {
    # Map common STT mishearings to canonical categories used by the IVR
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

    # Rings
    "ring": "rings",
    "rings": "rings",

    # Men's jewellery
    "mens jewellery": "men jewellery",
    "men's jewellery": "men jewellery",
    "mens jewelry": "men jewellery",
    "men's jewelry": "men jewellery",

    # Vintage diamonds
    "diamond": "vintage diamonds",
    "diamonds": "vintage diamonds",
    "vintage diamond": "vintage diamonds",
    "vintage diamonds": "vintage diamonds",
}

DEFAULT_GREETINGS = {
    "hi-IN": "Namaste, welcome to Jadau.",
    "en-IN": "Namaste, welcome to Jadau.",
}

DEFAULT_IVR_PROMPTS = {
    # Main menu - intent selection
    "reprompt": "I did not catch your response. Please say Try Near You, Price Request, General Inquiry, or Order Status.",
    "menu": "Please choose one of the following options: Try Near You, Price Request, General Inquiry, or Order Status.",
    "invalid": "Sorry, I didn't understand that. Please try again.",
    
    # Name collection - asked after intent selection
    "name_prompt": "May I have your name please, so that we can provide you with more specific assistance?",
    "name_profanity_failed_prompt": "I'm sorry, I couldn't accept that name. Could you please tell me your name again?",
    
    # After General Inquiry or Try Near You - product or category
    "assist_type_prompt": "Would you like assistance with a specific product or a product category?",
    "product_category_followup_prompt": "Before we proceed, please tell me which category this product belongs to: necklace, bangles, bracelets, earrings, rings, accessories, curated combination, men jewellery, or vintage diamonds.",
    
    # Product Name collection
    "product_id_prompt": "Please provide the product name for the item you're referring to (for example: 'Polki Necklace 123').",
    
    # Category name collection  
    "category_prompt": "Kindly mention the category name you're looking for.",
    "category_menu_prompt": "Please choose one of the categories: necklace, bangles, bracelets, earrings, rings, accessories, curated combination, men jewellery, or vintage diamonds.",
    
    # Price request - ask for product name
    "price_request_prompt": "Please provide the product name so I can check the pricing details for you.",
    "price_product_prompt": "Please provide the product name so I can check the pricing details for you.",

    # Order status prompts
    "order_status_prompt": "Please tell me your order ID or tracking number so I can check the status.",
    "order_id_prompt": "Please tell me your order ID or tracking number so I can check the status.",
    "order_status_not_ready": "Your order is not ready yet.",
    "order_status_shipped": "Your order has been shipped.",
    "order_status_no_orders": "Please place an order before checking the status.",
    
    # Confirmation before connecting to agent
    "confirmation": "Thank you. While I connect you to our agent for further assistance, please briefly describe your query.",
    "description_prompt": "Please briefly describe what you are looking for so our expert can prepare before picking up.",
    
    # Connection announcement
    "connecting": "Please wait while we connect you to our expert.",
    
    # Default fallback message when no agent available
    "no_agent": "Sorry, we cannot connect your call right now. Please try again later.",
}
