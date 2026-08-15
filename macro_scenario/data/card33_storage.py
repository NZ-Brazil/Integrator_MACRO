"""Card 33 - Underground CO2 storage: annual injection allowance per basin.

Source: 24_30_33.xlsx, sheet "33. Underground CO2 storage". The numbers are the
maximum annual injection rate and go into every nodes_<period>.json as they are.

Option A does not write a number: it switches CO2StorageConstraint off.
A None is a placeholder to be filled in later - the basin keeps the value the
case already has and the run reports it.
"""

CONSTRAINT = "CO2StorageConstraint"

# Basins in the case. co2_storage_Ceara is in the case but not yet in the sheet.
BASINS = [
    "co2_storage_Parana",
    "co2_storage_Santos",
    "co2_storage_Campos",
    "co2_storage_Sao_Francisco",
    "co2_storage_Reconcavo",
    "co2_storage_Sergipe_Alagoas",
    "co2_storage_Potiguar",
    "co2_storage_Parecis",
    "co2_storage_Espirito_Santo",
    "co2_storage_Ceara",
]

# None = placeholder, still to be defined
STORAGE = {
    "A": None,  # storage not allowed: the constraint is turned off
    "B": {
        "co2_storage_Parana": 332000000,
        "co2_storage_Santos": 38000000,
        "co2_storage_Campos": 700000,
        "co2_storage_Sao_Francisco": 108000000,
        "co2_storage_Reconcavo": 7000000,
        "co2_storage_Sergipe_Alagoas": 700000,
        "co2_storage_Potiguar": 700000,
        "co2_storage_Parecis": 89000000,
        "co2_storage_Espirito_Santo": 4000000,
        "co2_storage_Ceara": 300000,
    },
    "C": {
        "co2_storage_Parana": 894000000,
        "co2_storage_Santos": 75000000,
        "co2_storage_Campos": 1500000,
        "co2_storage_Sao_Francisco": 584000000,
        "co2_storage_Reconcavo": 8000000,
        "co2_storage_Sergipe_Alagoas": 1400000,
        "co2_storage_Potiguar": 900000,
        "co2_storage_Parecis": 276000000,
        "co2_storage_Espirito_Santo": 4000000,
        "co2_storage_Ceara": 700000,
    },
}
