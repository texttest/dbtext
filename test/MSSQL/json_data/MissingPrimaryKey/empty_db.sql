

CREATE TABLE wildlife (
    internalId        INT IDENTITY(1,1),
    name        VARCHAR(100),
    type        VARCHAR(16),
    PRIMARY KEY (internalId)
);


CREATE TABLE observations (
    internalId        INT IDENTITY(1,1),
    date         DATE,
    wildlifeId   INT,
    PRIMARY KEY (internalId),
    FOREIGN KEY (wildlifeId) REFERENCES wildlife(internalId)
);
