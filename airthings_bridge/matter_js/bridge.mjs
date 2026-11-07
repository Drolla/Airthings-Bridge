// Matter bridge process of the Airthings Bridge, run by
// airthings_bridge/consumers/matter.py.
//
// Copyright (C) 2026 Andreas Drollinger
// See the file "LICENSE" for information on usage and redistribution of this
// file, and for a DISCLAIMER OF ALL WARRANTIES.
//
// Reads JSON lines on stdin: "init" (storage, port, pairing data, endpoints),
// "update" (cluster states by endpoint ID) and "stop". Writes JSON lines on
// stdout: "ready", "pairing" and "fabrics". Logs to stderr.

import { randomBytes, randomInt } from "node:crypto";
import { createInterface } from "node:readline";

// matter.js logs to the console, stdout is kept for the messages. matter.js
// is imported afterwards.
for (const method of ["log", "info", "debug", "warn"]) console[method] = console.error;

// The Python side stops the process, also if the signals reach the whole
// process group (Ctrl+C) or control group (systemd)
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => {});

const { Endpoint, Environment, Logger, ServerNode, StorageService, VendorId } =
    await import("@matter/main");
const { AggregatorEndpoint } = await import("@matter/main/endpoints/aggregator");
const { AirQualitySensorDevice } = await import("@matter/main/devices/air-quality-sensor");
const behaviors = await import("@matter/main/behaviors");

const logger = Logger.get("AirthingsBridge");

// Cluster servers by the cluster names of matter.py
const CLUSTERS = {
    airQuality: behaviors.AirQualityServer.with("Fair"),
    temperatureMeasurement: behaviors.TemperatureMeasurementServer,
    relativeHumidityMeasurement: behaviors.RelativeHumidityMeasurementServer,
    pressureMeasurement: behaviors.PressureMeasurementServer,
    radonConcentrationMeasurement:
        behaviors.RadonConcentrationMeasurementServer.with("NumericMeasurement"),
    carbonDioxideConcentrationMeasurement:
        behaviors.CarbonDioxideConcentrationMeasurementServer.with("NumericMeasurement"),
    totalVolatileOrganicCompoundsConcentrationMeasurement:
        behaviors.TotalVolatileOrganicCompoundsConcentrationMeasurementServer.with(
            "NumericMeasurement"),
    powerSource: behaviors.PowerSourceServer.with("Battery"),
};

// Matter specification 5.1.7.1
const INVALID_PASSCODES = [0, 11111111, 22222222, 33333333, 44444444, 55555555, 66666666,
    77777777, 88888888, 99999999, 12345678, 87654321];

const BRIDGE_NAME = "Airthings Bridge";

let server;
const endpoints = new Map();

function send(message) {
    process.stdout.write(JSON.stringify(message) + "\n");
}

function fabricCount() {
    return Object.keys(server.state.commissioning.fabrics).length;
}

function sendPairing() {
    const { manualPairingCode, qrPairingCode } = server.state.commissioning.pairingCodes;
    send({ type: "pairing", manual: manualPairingCode, qr: qrPairingCode });
}

// Pairing data, serial number and unique ID, generated at the first start and
// stored
async function pairingData(passcode, discriminator) {
    const storage = await Environment.default.get(StorageService).open("bridge");
    const context = storage.createContext("pairing");
    let randomPasscode;
    do {
        randomPasscode = randomInt(1, 99999999);
    } while (INVALID_PASSCODES.includes(randomPasscode));
    const data = {
        passcode: passcode ?? await context.get("passcode", randomPasscode),
        discriminator: discriminator ?? await context.get("discriminator", randomInt(4096)),
        serialNumber: await context.get("serialNumber", randomBytes(8).toString("hex")),
        uniqueId: await context.get("uniqueId", randomBytes(16).toString("hex")),
    };
    await context.set(data);
    await storage.close();
    return data;
}

async function init({ storage, port, version, versionNumber, passcode, discriminator, logLevel,
    endpoints: specs }) {
    Logger.format = "plain";
    Logger.level = logLevel;
    Environment.default.vars.set("storage.path", storage);
    const pairing = await pairingData(passcode, discriminator);

    server = await ServerNode.create({
        id: "airthings-bridge",
        network: { port },
        commissioning: { passcode: pairing.passcode, discriminator: pairing.discriminator },
        productDescription: { name: BRIDGE_NAME, deviceType: AggregatorEndpoint.deviceType },
        basicInformation: {
            vendorName: BRIDGE_NAME,
            vendorId: VendorId(0xfff1), // Test vendor ID
            productId: 0x8000,
            productName: BRIDGE_NAME,
            productLabel: "Matter bridge", // Without vendor name
            nodeLabel: BRIDGE_NAME,
            hardwareVersion: 1,
            hardwareVersionString: "1",
            softwareVersion: versionNumber,
            softwareVersionString: version,
            serialNumber: pairing.serialNumber,
            uniqueId: pairing.uniqueId,
        },
    });
    const aggregator = new Endpoint(AggregatorEndpoint, { id: "aggregator" });
    await server.add(aggregator);
    for (const { id, clusters, state } of specs) {
        const type = AirQualitySensorDevice.with(
            behaviors.BridgedDeviceBasicInformationServer, ...clusters.map(name => CLUSTERS[name]));
        const endpoint = new Endpoint(type, { id, ...state });
        await aggregator.add(endpoint);
        endpoints.set(id, endpoint);
    }

    server.events.commissioning.fabricsChanged.on(() =>
        send({ type: "fabrics", fabrics: fabricCount() }));
    server.lifecycle.decommissioned.on(sendPairing);
    await server.start();
    send({ type: "ready", fabrics: fabricCount() });
    if (!server.lifecycle.isCommissioned) sendPairing();
}

async function update({ states }) {
    for (const [id, state] of Object.entries(states)) {
        await endpoints.get(id)?.set(state);
    }
}

async function stop() {
    await server?.close();
    process.exit(0);
}

// The messages are handled one after the other. A failed initialization ends
// the process, a failed update is only logged.
let queue = Promise.resolve();
const lines = createInterface({ input: process.stdin });
lines.on("line", line => {
    queue = queue.then(async () => {
        const message = JSON.parse(line);
        if (message.type === "init") {
            await init(message).catch(error => {
                logger.error(error);
                process.exit(1);
            });
        } else if (message.type === "update") {
            await update(message);
        } else if (message.type === "stop") {
            await stop();
        }
    }).catch(error => logger.error(error));
});
// Python side ended
lines.on("close", () => {
    queue = queue.then(stop);
});
