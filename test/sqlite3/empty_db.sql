CREATE TABLE wildlife
(
    internalId INTEGER PRIMARY KEY AUTOINCREMENT,
    name       VARCHAR(100),
    type       VARCHAR(16)
);


CREATE TABLE observations
(
    internalId INTEGER PRIMARY KEY AUTOINCREMENT,
    date       DATE,
    wildlifeId INT,
    FOREIGN KEY (wildlifeId) REFERENCES wildlife (internalId)
);
