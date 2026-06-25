#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""config.py — ScientificMonitor: full configuration for 12-agent system."""

PUBMED_EMAIL = "t.kislev@stardust-initiative.com"
PORT         = 5759

# ── Search keywords ──────────────────────────────────────────────────────────
SAI_KEYWORDS = [
    "stratospheric aerosol injection",
    "stratospheric aerosol geoengineering",
    "solar radiation management stratosphere",
    "SAI geoengineering",
    "heterogeneous uptake aerosol stratosphere",
    "silica aerosol stratosphere",
    "SiO2 aerosol stratosphere",
    "calcium carbonate aerosol stratosphere",
    "CaCO3 aerosol geoengineering",
    "polar stratospheric cloud heterogeneous chemistry",
    "PSC ozone chemistry",
    "ozone depletion aerosol stratosphere",
    "sulfate aerosol stratosphere ozone",
    "N2O5 aerosol heterogeneous",
    "ClONO2 aerosol hydrolysis",
    "halogen activation stratospheric aerosol",
    "aerosol optical depth stratosphere geoengineering",
    "stratospheric aerosol loading climate",
    "geoengineering aerosol particle size",
    "Pinatubo stratospheric chemistry aerosol",
    "sulfuric acid droplet stratosphere",
    "aerosol surface area density ozone",
    "reactive nitrogen stratosphere aerosol",
    "HOBr heterogeneous uptake aerosol",
    "BrONO2 aerosol",
]

EXCLUDE_KEYWORDS = [
    "marine cloud brightening", "cloud seeding", "cirrus cloud thinning",
    " CCT ", " MCB ", "ocean alkalinity enhancement", "direct air capture",
    "enhanced weathering", "bioenergy carbon capture", "BECCS",
    " CDR ", "tropospheric aerosol health", "urban air pollution aerosol",
    "wildfire smoke aerosol", "sea salt aerosol",
]

# ── Stardust key claims for contradiction checking ────────────────────────────
STARDUST_CLAIMS = {
    "safe_silica":    ["silica aerosol safe", "SiO2 non-reactive ozone", "silica minimal ozone"],
    "heterogeneous":  ["heterogeneous uptake silica", "surface chemistry SiO2", "silica uptake coefficient"],
    "safety_profile": ["safe aerosol material stratosphere", "benign aerosol SAI"],
    "calcite_alt":    ["calcite aerosol ozone neutral", "CaCO3 non-harmful ozone"],
}

CONTRADICTION_TRIGGERS = [
    "silica ozone depletion", "SiO2 ozone loss", "silica heterogeneous ozone",
    "aerosol surface chemistry ozone damage", "SAI termination shock severe",
    "geoengineering monsoon failure", "SAI crop failure", "stratospheric aerosol toxic",
    "SAI irreversible damage", "geoengineering catastrophic outcome",
]

NEGATIVE_TRIGGERS = [
    "SAI risks outweigh benefits", "geoengineering hazardous", "stratospheric aerosol harmful",
    "SAI dangerous side effects", "geoengineering ban", "aerosol injection prohibited",
    "SAI governance failure", "startup geoengineering reckless", "unilateral geoengineering",
]

# ── Tracked academics — ALL red priority ─────────────────────────────────────
TRACKED_ACADEMICS = [
    # --- Collaborators ---
    {"name": "Vicki Grassian",      "org": "UC San Diego / Scripps",              "group": "collaborator"},
    {"name": "Dan Cziczo",          "org": "Purdue University",                   "group": "collaborator"},
    {"name": "Tzemah Kislev",       "org": "Stardust Initiative",                 "group": "collaborator", "role": "Founder"},
    # --- Top world researchers ---
    {"name": "Alan Robock",         "org": "Rutgers University",                  "group": "primary"},
    {"name": "Ben Kravitz",         "org": "Indiana University",                  "group": "primary", "role": "Discussion Leader"},
    {"name": "Frank Keutsch",       "org": "Harvard University",                  "group": "primary"},
    {"name": "James Haywood",       "org": "University of Exeter",                "group": "primary"},
    {"name": "Simone Tilmes",       "org": "NCAR",                                "group": "primary", "role": "Speaker"},
    {"name": "Daniele Visioni",     "org": "Cornell University",                  "group": "primary", "role": "Vice Chair"},
    {"name": "Michael Diamond",     "org": "Florida State University",            "group": "primary", "role": "Chair"},
    {"name": "Lili Xia",            "org": "Rutgers University",                  "group": "primary", "role": "Chair"},
    {"name": "Christopher Field",   "org": "Stanford University",                 "group": "primary", "role": "Discussion Leader"},
    {"name": "Kate Ricke",          "org": "UCSD",                                "group": "primary", "role": "Discussion Leader"},
    {"name": "Douglas MacMartin",   "org": "Cornell University",                  "group": "primary"},
    {"name": "Benjamin Wagman",     "org": "Sandia National Labs",                "group": "primary"},
    {"name": "James Hurrell",       "org": "Colorado State University",           "group": "primary", "role": "Speaker"},
    {"name": "Jared Farley",        "org": "Cornell University",                  "group": "primary", "role": "Speaker"},
    {"name": "Jasper Kok",          "org": "UCLA",                                "group": "primary", "role": "Speaker"},
    {"name": "Edwin Kite",          "org": "University of Chicago",               "group": "primary", "role": "Speaker"},
    {"name": "Fangqun Yu",          "org": "University at Albany",                "group": "primary", "role": "Speaker"},
    {"name": "Graham Feingold",     "org": "NOAA",                                "group": "primary", "role": "Speaker"},
    {"name": "Johannes Quaas",      "org": "Leipzig University",                  "group": "primary", "role": "Speaker"},
    {"name": "Patrick Keys",        "org": "Boston University",                   "group": "primary", "role": "Speaker"},
    {"name": "Raymond Shaw",        "org": "Michigan Tech",                       "group": "primary", "role": "Speaker"},
    {"name": "Jessica Medrado",     "org": "SRI International",                   "group": "primary", "role": "Speaker"},
    {"name": "Mingyi Wang",         "org": "University of Chicago",               "group": "primary", "role": "Speaker"},
    {"name": "Phoebe Zarnetske",    "org": "Michigan State University",           "group": "primary", "role": "Speaker"},
    {"name": "Yingxiao Zhang",      "org": "NCAR",                                "group": "primary", "role": "Speaker"},
    {"name": "Yuanchao Fan",        "org": "Tsinghua University",                 "group": "primary", "role": "Speaker"},
    {"name": "Govindasamy Bala",    "org": "Indian Institute of Science",         "group": "primary"},
    {"name": "Robert Wood",         "org": "University of Washington",            "group": "primary"},
    # --- NOAA/Government ---
    {"name": "Amy Butler",          "org": "NOAA Chemical Sciences Laboratory",   "group": "government"},
    {"name": "Joshua Schwarz",      "org": "NOAA",                                "group": "government"},
    {"name": "Richard Moore",       "org": "NASA Langley",                        "group": "government"},
    {"name": "Gregory Frost",       "org": "NOAA",                                "group": "government"},
    {"name": "Ewa Bednarz",         "org": "CIRES/NOAA CSL",                      "group": "government"},
    {"name": "Jianhao Zhang",       "org": "University of Colorado Boulder / NOAA CSL", "group": "government"},
]

# ── Tracked organizations ─────────────────────────────────────────────────────
TRACKED_ORGS = [
    {
        "name": "Make Sunset",
        "type": "commercial",
        "search_terms": ["Make Sunset geoengineering", "makesunset stratospheric", "Luke Iseman SAI"],
        "key_people": ["Luke Iseman"],
    },
    {
        "name": "Reflective",
        "type": "commercial",
        "search_terms": ["Reflective geoengineering", "Ali Akherati aerosol",
                         "Alistair Duffey stratospheric", "Susanne Baur aerosol", "Marianna Linz SAI"],
        "key_people": ["Ali Akherati", "Alistair Duffey", "Susanne Baur", "Marianna Linz"],
    },
    {
        "name": "Parasol Labs",
        "type": "commercial",
        "search_terms": ["Parasol Labs SAI", "Hudson Gilmer stratospheric", "Parasol geoengineering"],
        "key_people": ["Hudson Gilmer"],
    },
    {
        "name": "SilverLining",
        "type": "nonprofit",
        "search_terms": ["SilverLining geoengineering", "Corinne Hartin SRM", "Silver Lining SAI"],
        "key_people": ["Corinne Hartin"],
    },
    {
        "name": "Stardust Initiative",
        "type": "own",
        "search_terms": ["Stardust Initiative SAI", "Amyad Spector geoengineering"],
        "key_people": ["Amyad Spector", "Tzemah Kislev"],
    },
    {
        "name": "Planetary Sunshade Foundation",
        "type": "nonprofit",
        "search_terms": ["Planetary Sunshade Foundation", "Morgan Goodwin geoengineering SAI"],
        "key_people": ["Morgan Goodwin"],
    },
    {
        "name": "ARIA UK",
        "type": "government",
        "search_terms": ["ARIA UK geoengineering", "Mark Symes climate intervention", "ARIA stratospheric"],
        "key_people": ["Mark Symes"],
    },
]

# ── SAI conferences ───────────────────────────────────────────────────────────
SAI_CONFERENCES = [
    {"name": "AGU Fall Meeting",     "abbr": "AGU",  "search": "AGU stratospheric aerosol injection"},
    {"name": "EGU General Assembly", "abbr": "EGU",  "search": "EGU stratospheric aerosol geoengineering"},
    {"name": "AMS Annual Meeting",   "abbr": "AMS",  "search": "AMS stratospheric aerosol climate"},
    {"name": "Gordon Research Conference on Geoengineering", "abbr": "GRC", "search": "Gordon Conference SAI"},
    {"name": "iSAI (Invited SAI Workshop)", "abbr": "iSAI", "search": "iSAI stratospheric aerosol workshop"},
]

# ── SRM/SAI funders ───────────────────────────────────────────────────────────
SAI_FUNDERS = [
    "National Science Foundation",
    "NOAA",
    "NASA",
    "Department of Energy",
    "Harvard Solar Geoengineering Research Program",
    "Fund for Innovative Climate and Energy Research",
    "European Research Council",
    "Grantham Foundation",
    "Open Philanthropy",
    "SilverLining Safe Climate Research Initiative",
    "DEGREES Initiative",
]
