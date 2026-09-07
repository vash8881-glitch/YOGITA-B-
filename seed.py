import os
from datetime import timedelta

from auth_utils import hash_pw, new_id, now_utc
from db import db

IMG = {
    "tomato": "https://images.unsplash.com/photo-1582284540020-8acbe03f4924?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjY2NjV8MHwxfHNlYXJjaHwxfHxmcmVzaCUyMHJlZCUyMHRvbWF0b2VzfGVufDB8fHx8MTc4NzUwNDU0M3ww&ixlib=rb-4.1.0&q=85",
    "tomato2": "https://images.unsplash.com/photo-1524593166156-312f362cada0?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjY2NjV8MHwxfHNlYXJjaHwzfHxmcmVzaCUyMHJlZCUyMHRvbWF0b2VzfGVufDB8fHx8MTc4NzUwNDU0M3ww&ixlib=rb-4.1.0&q=85",
    "potato": "https://images.pexels.com/photos/34429585/pexels-photo-34429585.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    "onion": "https://images.unsplash.com/photo-1779769600397-df23ac0e5f68?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzJ8MHwxfHNlYXJjaHwyfHxwb3RhdG9lcyUyMG9uaW9ucyUyMGdhcmxpYyUyMGdpbmdlcnxlbnwwfHx8fDE3ODc1MDQ1NDN8MA&ixlib=rb-4.1.0&q=85",
    "carrot": "https://images.unsplash.com/photo-1609842947419-ba4f04d5d60f?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2NjZ8MHwxfHNlYXJjaHwxfHxmcmVzaCUyMHZlZ2V0YWJsZXMlMjBtYXJrZXQlMjBiYXNrZXR8ZW58MHx8fHwxNzg3NTA0NDk0fDA&ixlib=rb-4.1.0&q=85",
    "cabbage": "https://images.unsplash.com/photo-1652860213441-6622f9fec77f?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2NjZ8MHwxfHNlYXJjaHw0fHxmcmVzaCUyMHZlZ2V0YWJsZXMlMjBtYXJrZXQlMjBiYXNrZXR8ZW58MHx8fHwxNzg3NTA0NDk0fDA&ixlib=rb-4.1.0&q=85",
    "cauliflower": "https://images.unsplash.com/photo-1690934164598-99267828e900?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2NjZ8MHwxfHNlYXJjaHwyfHxmcmVzaCUyMHZlZ2V0YWJsZXMlMjBtYXJrZXQlMjBiYXNrZXR8ZW58MHx8fHwxNzg3NTA0NDk0fDA&ixlib=rb-4.1.0&q=85",
    "spinach": "https://images.unsplash.com/photo-1574316071802-0d684efa7bf5?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjY2NzF8MHwxfHNlYXJjaHwyfHxzcGluYWNoJTIwY29yaWFuZGVyJTIwbGVhZnklMjBncmVlbnN8ZW58MHx8fHwxNzg3NTA0NTQzfDA&ixlib=rb-4.1.0&q=85",
    "coriander": "https://images.unsplash.com/photo-1576045057995-568f588f82fb?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjY2NzF8MHwxfHNlYXJjaHwxfHxzcGluYWNoJTIwY29yaWFuZGVyJTIwbGVhZnklMjBncmVlbnN8ZW58MHx8fHwxNzg3NTA0NTQzfDA&ixlib=rb-4.1.0&q=85",
    "capsicum": "https://images.unsplash.com/photo-1622031175804-3c70a3ae5ed3?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2NjZ8MHwxfHNlYXJjaHwzfHxmcmVzaCUyMHZlZ2V0YWJsZXMlMjBtYXJrZXQlMjBiYXNrZXR8ZW58MHx8fHwxNzg3NTA0NDk0fDA&ixlib=rb-4.1.0&q=85",
    "brinjal": "https://images.pexels.com/photos/37321079/pexels-photo-37321079.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    "okra": "https://images.pexels.com/photos/32465897/pexels-photo-32465897.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    "chilli": "https://images.unsplash.com/photo-1622031175804-3c70a3ae5ed3?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2NjZ8MHwxfHNlYXJjaHwzfHxmcmVzaCUyMHZlZ2V0YWJsZXMlMjBtYXJrZXQlMjBiYXNrZXR8ZW58MHx8fHwxNzg3NTA0NDk0fDA&ixlib=rb-4.1.0&q=85",
    "garlic": "https://images.unsplash.com/photo-1567752458426-b62144165409?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzJ8MHwxfHNlYXJjaHwxfHxwb3RhdG9lcyUyMG9uaW9ucyUyMGdhcmxpYyUyMGdpbmdlcnxlbnwwfHx8fDE3ODc1MDQ1NDN8MA&ixlib=rb-4.1.0&q=85",
    "ginger": "https://images.unsplash.com/photo-1567752458426-b62144165409?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzJ8MHwxfHNlYXJjaHwxfHxwb3RhdG9lcyUyMG9uaW9ucyUyMGdhcmxpYyUyMGdpbmdlcnxlbnwwfHx8fDE3ODc1MDQ1NDN8MA&ixlib=rb-4.1.0&q=85",
    "apple": "https://images.pexels.com/photos/3025236/pexels-photo-3025236.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    "banana": "https://images.unsplash.com/photo-1546630392-db5b1f04874a?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA2MjJ8MHwxfHNlYXJjaHw0fHxtYW5nbyUyMGJhbmFuYSUyMGFwcGxlJTIwb3JhbmdlJTIwZnJ1aXRzfGVufDB8fHx8MTc4NzUwNDU0M3ww&ixlib=rb-4.1.0&q=85",
    "orange": "https://images.unsplash.com/photo-1631815333087-9ccf8fa82166?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA2MjJ8MHwxfHNlYXJjaHwxfHxtYW5nbyUyMGJhbmFuYSUyMGFwcGxlJTIwb3JhbmdlJTIwZnJ1aXRzfGVufDB8fHx8MTc4NzUwNDU0M3ww&ixlib=rb-4.1.0&q=85",
    "mango": "https://images.unsplash.com/photo-1757281096599-b9165ba74008?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA2MjJ8MHwxfHNlYXJjaHwyfHxtYW5nbyUyMGJhbmFuYSUyMGFwcGxlJTIwb3JhbmdlJTIwZnJ1aXRzfGVufDB8fHx8MTc4NzUwNDU0M3ww&ixlib=rb-4.1.0&q=85",
    "fruits": "https://images.unsplash.com/photo-1546548970-71785318a17b?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NjZ8MHwxfHNlYXJjaHwzfHxmcmVzaCUyMGZydWl0cyUyMGNvbG9yZnVsJTIwYXNzb3J0bWVudHxlbnwwfHx8fDE3ODc1MDQ0MjR8MA&ixlib=rb-4.1.0&q=85",
    "spices": "https://images.unsplash.com/photo-1635355995448-77b02d33621d?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzNDR8MHwxfHNlYXJjaHwzfHxpbmRpYW4lMjBzcGljZXMlMjBwdWxzZXMlMjBncm9jZXJ5JTIwZmFybSUyMGZyZXNofGVufDB8fHx8MTc4NzUwNDQyNHww&ixlib=rb-4.1.0&q=85",
    "grains": "https://images.pexels.com/photos/1393382/pexels-photo-1393382.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    "basket": "https://images.unsplash.com/photo-1631021967261-c57ee4dfa9bb?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NTJ8MHwxfHNlYXJjaHwzfHxmcmVzaCUyMG9yZ2FuaWMlMjB2ZWdldGFibGVzJTIwYmFza2V0JTIwbWFya2V0fGVufDB8fHx8MTc4NzUwNDQyNHww&ixlib=rb-4.1.0&q=85",
    "leafy": "https://images.unsplash.com/photo-1617884638394-d9eef1b0f40e?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjY2NzF8MHwxfHNlYXJjaHw0fHxzcGluYWNoJTIwY29yaWFuZGVyJTIwbGVhZnklMjBncmVlbnN8ZW58MHx8fHwxNzg3NTA0NTQzfDA&ixlib=rb-4.1.0&q=85",
    "market": "https://images.unsplash.com/photo-1765031039845-4bb510dc8112?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzJ8MHwxfHNlYXJjaHwzfHxwb3RhdG9lcyUyMG9uaW9ucyUyMGdhcmxpYyUyMGdpbmdlcnxlbnwwfHx8fDE3ODc1MDQ1NDN8MA&ixlib=rb-4.1.0&q=85",
}

CATEGORIES = [
    {"id": "cat-vegetables", "name": {"en": "Vegetables", "hi": "सब्ज़ियाँ", "kn": "ತರಕಾರಿಗಳು", "mr": "भाज्या"}, "image": IMG["basket"], "sort_order": 1},
    {"id": "cat-fruits", "name": {"en": "Fruits", "hi": "फल", "kn": "ಹಣ್ಣುಗಳು", "mr": "फळे"}, "image": IMG["fruits"], "sort_order": 2},
    {"id": "cat-leafy", "name": {"en": "Leafy Vegetables", "hi": "पत्तेदार सब्ज़ियाँ", "kn": "ಎಲೆಕೊಸು ತರಕಾರಿ", "mr": "पानभाज्या"}, "image": IMG["leafy"], "sort_order": 3},
    {"id": "cat-organic", "name": {"en": "Organic", "hi": "ऑर्गेनिक", "kn": "ಸಾವಯವ", "mr": "सेंद्रिय"}, "image": IMG["carrot"], "sort_order": 4},
    {"id": "cat-grocery", "name": {"en": "Grocery", "hi": "किराना", "kn": "ದಾಣ್ಯ", "mr": "किराणा"}, "image": IMG["grains"], "sort_order": 5},
    {"id": "cat-combos", "name": {"en": "Combos", "hi": "कॉम्बो", "kn": "ಕಾಂಬೋ", "mr": "कॉम्बो"}, "image": IMG["market"], "sort_order": 6},
]


def P(sku, en, hi, kn, mr, cat, price, mrp, unit, stock, img, badges, fresh, cost, variants=None, popularity=0, rating=4.2, desc=""):
    return {
        "id": new_id(), "sku": sku,
        "name": {"en": en, "hi": hi, "kn": kn, "mr": mr},
        "description": {"en": desc or f"Farm-fresh {en.lower()} sourced daily from local farmers.", "hi": desc or f"स्थानीय किसानों से रोज़ाना लाई गई ताज़ी {hi}।", "kn": desc or f"ಸ್ಥಳೀಯ ರೈತರಿಂದ ದೈನಂದಿನವಾಗಿ ತರಲಾದ ತಾಜಾ {kn}.", "mr": desc or f"स्थानिक शेतकऱ्यांकडून रोज आणलेली ताजी {mr}."},
        "category_id": cat, "price": price, "mrp": mrp, "cost": cost, "unit": unit,
        "stock": stock, "low_stock_threshold": 10, "images": [img],
        "badges": badges, "is_active": True, "is_fresh": fresh,
        "variants": variants or [], "rating": rating, "rating_count": 40 + popularity,
        "popularity": popularity, "discount_percent": round((1 - price / mrp) * 100) if mrp > price else 0,
        "created_at": now_utc().isoformat(),
    }


def V(label, price, mrp, stock=50):
    return {"id": new_id(), "label": label, "price": price, "mrp": mrp, "stock": stock}


PRODUCTS = [
    P("VEG-TOM-001", "Tomato", "टमाटर", "ಟೊಮೇಟೊ", "टोमॅटो", "cat-vegetables", 32, 45, "1 kg", 120, IMG["tomato"], ["Daily Fresh", "Discount"], True, 24, [V("500 g", 18, 25), V("1 kg", 32, 45), V("2 kg", 60, 85)], 95, 4.4),
    P("VEG-POT-001", "Potato", "आलू", "ಆಲೂಗಡ್ಡೆ", "बटाटा", "cat-vegetables", 28, 38, "1 kg", 200, IMG["potato"], ["Best Seller"], True, 20, [V("500 g", 15, 20), V("1 kg", 28, 38), V("2 kg", 54, 72)], 120, 4.3),
    P("VEG-ONI-001", "Onion", "प्याज़", "ಈರುಳ್ಳಿ", "कांदा", "cat-vegetables", 35, 48, "1 kg", 180, IMG["onion"], ["Best Seller"], True, 26, [V("500 g", 19, 26), V("1 kg", 35, 48), V("2 kg", 66, 90)], 110, 4.2),
    P("VEG-CAR-001", "Carrot", "गाजर", "ಕ್ಯಾರೆಟ್", "गाजर", "cat-vegetables", 44, 60, "500 g", 90, IMG["carrot"], ["Fresh Today"], True, 33, [V("250 g", 24, 32), V("500 g", 44, 60), V("1 kg", 84, 110)], 70, 4.5),
    P("VEG-CAB-001", "Cabbage", "पत्ता गोभी", "ಎಲೆಕೋಸು", "कोबी", "cat-vegetables", 26, 35, "1 pc", 75, IMG["cabbage"], ["Local Delivery"], True, 18, [], 60, 4.1),
    P("VEG-CAU-001", "Cauliflower", "फूलगोभी", "ಹೂಕೋಸು", "फुलकोबी", "cat-vegetables", 38, 52, "1 pc", 60, IMG["cauliflower"], ["Fresh Today"], True, 28, [], 55, 4.3),
    P("VEG-CAP-001", "Capsicum", "शिमला मिर्च", "ಡೊಣ್ಣೆ ಮೆಣಸಿನಕಾಯಿ", "शिमला मिरची", "cat-vegetables", 58, 78, "500 g", 45, IMG["capsicum"], ["New"], True, 44, [V("250 g", 30, 40), V("500 g", 58, 78)], 40, 4.4),
    P("VEG-BRI-001", "Brinjal", "बैंगन", "ಬದನೆಕಾಯಿ", "वांगी", "cat-vegetables", 36, 50, "500 g", 65, IMG["brinjal"], ["Discount"], True, 27, [], 48, 4.0),
    P("VEG-OKR-001", "Lady Finger", "भिंडी", "ಬೆಂಡೆಕಾಯಿ", "भेंडी", "cat-vegetables", 42, 58, "500 g", 8, IMG["okra"], ["Limited Stock"], True, 32, [], 52, 4.3),
    P("VEG-CHI-001", "Green Chilli", "हरी मिर्च", "ಹಸಿಮೆಣಸಿನಕಾಯಿ", "हिरवी मिरची", "cat-vegetables", 22, 30, "250 g", 100, IMG["chilli"], ["Daily Fresh"], True, 15, [], 66, 4.2),
    P("VEG-GAR-001", "Garlic", "लहसुन", "ಬೆಳ್ಳುಳ್ಳಿ", "लसूण", "cat-vegetables", 90, 120, "250 g", 80, IMG["garlic"], [], True, 70, [], 44, 4.5),
    P("VEG-GIN-001", "Ginger", "अदरक", "ಶುಂಠಿ", "आलं", "cat-vegetables", 70, 95, "250 g", 85, IMG["ginger"], [], True, 52, [], 46, 4.4),
    P("LFY-SPI-001", "Spinach", "पालक", "ಪಾಲಕ್", "पालक", "cat-leafy", 25, 35, "1 bunch", 70, IMG["spinach"], ["Daily Fresh", "Fresh Today"], True, 16, [], 88, 4.6),
    P("LFY-COR-001", "Coriander", "धनिया", "ಕೊತ್ತಂಬರಿ", "कोथिंबीर", "cat-leafy", 15, 22, "1 bunch", 95, IMG["coriander"], ["Daily Fresh"], True, 9, [], 92, 4.5),
    P("ORG-VEG-001", "Organic Veg Basket", "ऑर्गेनिक सब्ज़ी टोकरी", "ಸಾವಯವ ತರಕಾರಿ ಬುಟ್ಟಿ", "सेंद्रिय भाजी टोपली", "cat-organic", 349, 449, "3 kg", 25, IMG["carrot"], ["Organic", "Discount"], True, 260, [], 35, 4.7),
    P("ORG-CAR-001", "Organic Carrot", "ऑर्गेनिक गाजर", "ಸಾವಯವ ಕ್ಯಾರೆಟ್", "सेंद्रिय गाजर", "cat-organic", 68, 90, "500 g", 40, IMG["carrot"], ["Organic"], True, 50, [], 30, 4.6),
    P("FRU-APP-001", "Apple Shimla", "सेब", "ಸೇಬು", "सफरचंद", "cat-fruits", 145, 180, "1 kg", 60, IMG["apple"], ["Best Seller"], False, 115, [V("500 g", 78, 95), V("1 kg", 145, 180)], 85, 4.5),
    P("FRU-BAN-001", "Banana Robusta", "केला", "ಬಾಳೆಹಣ್ಣು", "केळी", "cat-fruits", 45, 60, "1 dozen", 110, IMG["banana"], ["Daily Fresh"], True, 32, [V("6 pcs", 25, 32), V("1 dozen", 45, 60)], 100, 4.3),
    P("FRU-ORA-001", "Orange Nagpur", "संतरा", "ಕಿತ್ತಳೆ", "संत्रा", "cat-fruits", 95, 125, "1 kg", 55, IMG["orange"], ["Fresh Today"], True, 72, [], 58, 4.4),
    P("FRU-MAN-001", "Mango Alphonso", "आम", "ಮಾವು", "आंबा", "cat-fruits", 299, 399, "1 kg", 35, IMG["mango"], ["New", "Best Seller"], True, 240, [V("500 g", 160, 210), V("1 kg", 299, 399)], 130, 4.8),
    P("GRO-ATT-001", "Whole Wheat Atta", "गेहूं आटा", "ಗೋಧಿ ಹಿಟ್ಟು", "गव्हाचे पीठ", "cat-grocery", 265, 320, "5 kg", 50, IMG["grains"], ["Discount"], False, 230, [V("1 kg", 58, 70), V("5 kg", 265, 320), V("10 kg", 510, 620)], 75, 4.4),
    P("GRO-DAL-001", "Toor Dal", "तूर दाल", "ತೊಗರಿ ಬೇಳೆ", "तूर डाळ", "cat-grocery", 155, 185, "1 kg", 65, IMG["spices"], [], False, 132, [V("500 g", 82, 98), V("1 kg", 155, 185)], 68, 4.3),
    P("GRO-RIC-001", "Sona Masoori Rice", "सोना मसूरी चावल", "ಸೋನಾ ಮಸೂರಿ ಅಕ್ಕಿ", "सोना मसुरी तांदूळ", "cat-grocery", 420, 499, "5 kg", 40, IMG["grains"], ["Best Seller"], False, 375, [], 62, 4.5),
    P("CMB-FAM-001", "Family Veg Combo", "फैमिली वेज कॉम्बो", "ಕುಟುಂಬ ತರಕಾರಿ ಕಾಂಬೋ", "फॅमिली भाजी कॉम्बो", "cat-combos", 499, 650, "5 kg pack", 20, IMG["market"], ["Discount", "Best Seller"], True, 400, [], 90, 4.6),
    P("CMB-DLY-001", "Daily Essentials Combo", "दैनिक ज़रूरत कॉम्बो", "ದೈನಂದಿನ ಅಗತ್ಯ ಕಾಂಬೋ", "दैनंदिन गरजा कॉम्बो", "cat-combos", 199, 260, "2 kg pack", 30, IMG["basket"], ["Discount"], True, 155, [], 78, 4.4),
]

BANNERS = [
    {"id": new_id(), "title": {"en": "Farm Fresh Vegetables", "hi": "ताज़ी फार्म सब्ज़ियाँ", "kn": "ತಾಜಾ ತರಕಾರಿಗಳು", "mr": "ताज्या शेतातील भाज्या"},
     "subtitle": {"en": "Up to 30% off on daily essentials", "hi": "रोज़ की ज़रूरतों पर 30% तक छूट", "kn": "ದೈನಂದಿನ ಅಗತ್ಯಗಳ ಮೇಲೆ 30% ರಷ್ಟು ರಿಯಾಯಿತಿ", "mr": "रोजच्या गरजांवर 30% पर्यंत सूट"},
     "image": IMG["basket"], "cta": "Shop Now", "link": "/products?category=cat-vegetables", "sort_order": 1, "is_active": True},
    {"id": new_id(), "title": {"en": "Season's Best Fruits", "hi": "सीज़न के बेहतरीन फल", "kn": "ಋತುವಿನ ಅತ್ಯುತ್ತಮ ಹಣ್ಣುಗಳು", "mr": "हंगामातील सर्वोत्तम फळे"},
     "subtitle": {"en": "Alphonso mangoes are here!", "hi": "अल्फांसो आम आ गए!", "kn": "ಅಲ್ಫಾನ್ಸೊ ಮಾವು ಬಂದಿದೆ!", "mr": "अल्फान्सो आंबे आले!"},
     "image": IMG["fruits"], "cta": "Order Now", "link": "/products?category=cat-fruits", "sort_order": 2, "is_active": True},
    {"id": new_id(), "title": {"en": "Daily Needs, One Place", "hi": "रोज़ की ज़रूरतें, एक जगह", "kn": "ದೈನಂದಿನ ಅಗತ್ಯಗಳು, ಒಂದೇ ಸ್ಥಳ", "mr": "रोजच्या गरजा, एकाच ठिकाणी"},
     "subtitle": {"en": "Grocery staples at mandi prices", "hi": "मंडी भाव पर किराना सामान", "kn": "ಮಂಡಿ ಬೆಲೆಯಲ್ಲಿ ದಾಣ್ಯ", "mr": "मंडई भावात किराणा"},
     "image": IMG["spices"], "cta": "Explore", "link": "/products?category=cat-grocery", "sort_order": 3, "is_active": True},
]

DEFAULT_SETTINGS = {
    "store_name": os.environ.get("STORE_NAME", "SabziMandi Fresh"),
    "phone": os.environ.get("STORE_PHONE", ""),
    "whatsapp": os.environ.get("STORE_WHATSAPP", ""),
    "email": os.environ.get("STORE_EMAIL", ""),
    "address": os.environ.get("STORE_ADDRESS", ""),
    "gst_number": os.environ.get("GST_NUMBER", ""),
    "logo": "",
    "favicon": "",
    "gst_percent": 5,
    "delivery": {
        "pincodes": ["560001", "560002", "560003", "560004", "560005", "560008", "560011", "560034", "560038", "560066"],
        "areas": ["Indiranagar", "Koramangala", "HSR Layout", "Whitefield", "MG Road"],
        "fee_tiers": [{"max": 199, "fee": 30}, {"max": 499, "fee": 20}, {"max": None, "fee": 0}],
        "min_order": 0,
        "estimated": "Within 2 hours",
        "slots": ["Morning 6 AM - 9 AM", "Midday 11 AM - 1 PM", "Evening 5 PM - 8 PM"],
    },
    "loyalty": {"per_amount": 100, "points": 1, "point_value": 1},
    "payments": {"cod": True, "upi": True, "upi_id": "sabzimandi@upi", "razorpay_key_id": "", "stripe_key": ""},
    "seo": {"title": "SabziMandi Fresh - Farm Fresh Vegetables Delivered", "description": "Order fresh vegetables, fruits and groceries online with fast local delivery.", "keywords": "vegetables, fruits, grocery, fresh, delivery", "og_image": ""},
}


async def seed():
    now = now_utc().isoformat()

    admin_email = os.environ.get("ADMIN_EMAIL", "admin@sabzimandi.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@123")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "id": new_id(), "name": "Super Admin", "email": admin_email,
            "password_hash": hash_pw(admin_password), "role": "super_admin",
            "wallet_balance": 0.0, "loyalty_points": 0, "created_at": now,
        })
    elif not __import__("bcrypt").checkpw(admin_password.encode(), existing["password_hash"].encode()):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_pw(admin_password)}})

    if await db.categories.count_documents({}) == 0:
        for c in CATEGORIES:
            c = dict(c)
            c["is_active"] = True
            await db.categories.insert_one(c)

    if await db.products.count_documents({}) == 0:
        for p in PRODUCTS:
            await db.products.insert_one(dict(p))

    if await db.banners.count_documents({}) == 0:
        for b in BANNERS:
            await db.banners.insert_one(dict(b))

    if not await db.settings.find_one({"key": "store"}):
        await db.settings.insert_one({"key": "store", "value": DEFAULT_SETTINGS})

    if await db.coupons.count_documents({}) == 0:
        expiry = (now_utc() + timedelta(days=30)).isoformat()
        await db.coupons.insert_many([
            {"id": new_id(), "code": "FRESH50", "type": "fixed", "value": 50, "min_order": 299, "max_discount": None, "expiry": expiry, "usage_limit": 500, "used_count": 0, "is_active": True},
            {"id": new_id(), "code": "SABZI10", "type": "percent", "value": 10, "min_order": 499, "max_discount": 150, "expiry": expiry, "usage_limit": None, "used_count": 0, "is_active": True},
        ])

    if await db.offers.count_documents({}) == 0:
        tomato = await db.products.find_one({"sku": "VEG-TOM-001"}, {"_id": 0, "id": 1, "name": 1, "images": 1, "price": 1, "mrp": 1, "unit": 1})
        if tomato:
            await db.offers.insert_one({
                "id": new_id(), "product_id": tomato["id"], "product": tomato,
                "offer_price": 25, "message": "Today's Fresh Offer - Farm tomatoes at mandi price!",
                "start_at": (now_utc() - timedelta(hours=1)).isoformat(),
                "end_at": (now_utc() + timedelta(hours=10)).isoformat(),
                "discount_percent": round((1 - 25 / tomato["mrp"]) * 100),
                "is_active": True, "created_at": now,
            })


async def create_indexes():
    async def safe(coro):
        try:
            await coro
        except Exception:
            pass
    await safe(db.users.drop_index("mobile_1"))
    await safe(db.users.drop_index("email_1"))
    await safe(db.otps.drop_index("expires_at_1"))
    await safe(db.users.create_index("mobile", unique=True, partialFilterExpression={"mobile": {"$type": "string"}}))
    await safe(db.users.create_index("email", unique=True, partialFilterExpression={"email": {"$type": "string"}}))
    await safe(db.products.create_index("sku", unique=True))
    await safe(db.products.create_index("category_id"))
    await safe(db.orders.create_index("id", unique=True))
    await safe(db.orders.create_index("user_id"))
    await safe(db.orders.create_index("created_at"))
    await safe(db.otps.create_index("identifier"))
    await safe(db.otps.create_index("expires_at", expireAfterSeconds=300))
    await safe(db.carts.create_index("cart_token", unique=True))
    await safe(db.activity_logs.create_index("created_at"))
