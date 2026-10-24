# Robots and machinery

Load this when a change touches a robot, a machine's control software, or ROS 2. Each source was read on 2026-10-22.

## The EU Machinery Regulation

Regulation (EU) 2023/1230 applies from 2027-01-20 and replaces the Machinery Directive 2006/42/EC. Machinery placed on the market before that date follows the Directive. For software, it says:

- **Software can be a safety component.** Software that performs a safety function and is placed on the market on its own is a safety component (Art. 3(3) and Recital 19). It carries its own conformity assessment.
- **Protection against corruption** (Annex III, 1.1.9). Software and data critical to the machine's compliance are identified and protected against accidental or intentional corruption. The machine collects evidence of each intervention or modification, legitimate or not, and identifies the safety software installed. In a Spec, that's a signed update path, a read-only safety partition, and an intervention log.
- **Machine learning in a safety function** needs a third-party conformity assessment: a safety component or a machine with fully or partly self-evolving behaviour (Annex I, Part A).
- **AI in machinery is a sectoral rule now.** The AI Act's Digital Omnibus (Regulation (EU) 2026/1744) moved the Machinery Regulation from Section A to Section B of the AI Act's Annex I. So the Machinery Regulation, with delegated acts the Commission adds by 2028-08-02, sets a machine's AI duties.

Source: [the Commission's machinery page](https://single-market-economy.ec.europa.eu/sectors/mechanical-engineering/machinery_en).

## Robot safety standards

| Standard | Covers | Edition |
| --- | --- | --- |
| ISO 10218-1 | the industrial robot itself: inherently safe design, risk reduction, information for use | 2025 (published 2025-02-05), replacing 2011 |
| ISO 10218-2 | integrating industrial robot applications and robot cells | 2025 (published 2025-02-05), replacing 2011 |
| ISO 13482 | personal care robots: mobile servant, physical assistant, and person carrier | 2014; a second edition for service robots was at the FDIS ballot (emerging) |

A collaborative application is assessed for the whole cell, not only the robot arm. A speed or force limit lives in the safety controller, with its own tests. The application code never holds it. Sources: [ISO 10218-1](https://www.iso.org/standard/73933.html), [ISO 10218-2](https://www.iso.org/standard/73934.html), [ISO 13482](https://www.iso.org/standard/53820.html).

## ROS 2 security (SROS2)

SROS2 runs ROS 2 on DDS-Security, so each node authenticates, and topics are encrypted and access-controlled.

- Create a keystore (`ros2 security create_keystore`) and one enclave per node or process (`ros2 security create_enclave`). Keep the keystore's private keys out of the repository and the image.
- Run with `ROS_SECURITY_KEYSTORE` set, `ROS_SECURITY_ENABLE=true`, and `ROS_SECURITY_STRATEGY=Enforce`. Then a node without valid credentials can't join.
- Grant each enclave only the topics and services it needs, in its permissions file.
- **Test:** start a node with no enclave, or one outside its permissions, and check that it can neither publish a command nor subscribe to a protected topic.

The current ROS 2 distribution is Lyrical Luth (May 2026, supported to May 2031). Sources: [ros2/sros2](https://github.com/ros2/sros2) and [ROS 2 releases](https://docs.ros.org/en/rolling/Releases.html).

## Automotive SPICE (a pointer)

An automotive supplier's process is often assessed against Automotive SPICE. The current version is PAM 4.1 (August 2026), which replaced 4.0 (2023-11-29). aidd's loop gives evidence for many of its processes, such as requirements traced to tests, reviews, and configuration management. An assessment stays the assessor's. Source: [VDA QMC](https://vda-qmc.de/en/automotive-spice/).
