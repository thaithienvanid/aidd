# Try the design

Load this before a person sees a design that makes a guarantee, acts on events, runs in more than one setup, or gives a count. A design is shown on the way things go right, and it fails on the rest. So try to break it, and write down what happened. `aidd-team:data-model-design` points here from its design proof.

A change inside one module, with no event, no guarantee, and one setup, skips this file. An id in brackets is a standard of the skill's table.

## Who tries it

A reader who did not write the design runs each case in a fresh session with no chat history. The reader tags every point "ran" or "read". Prefer another model when one is available. A team with one model uses a fresh session of the same model, with none of the author's conversation. When two or more designs touch one model, one fresh reader writes one combined design. That reader lists each conflict with its proposed resolution for a person to decide.

## Each guarantee

A sentence with "never", "always", or "nothing is lost" is a claim. For each one, name the case that would break it. Walk that case through the design's own tables, and paste the result. A guarantee is a finding when no rule or table on the page already answers the case that would break it.

## Each event

An event can be lost, so stored state is the truth and an event only saves time. [k8s-api-conventions] For each event, name the stored state from which the same work is found when the event never arrives, and what reads that state. A warehouse that starts picking on `order.paid` also runs a nightly sweep for paid orders with no pick list. An event with no such state loses its work with the event.

## Each setup and each person

Walk one item through every setup that the design says it supports, and name who writes each fact there. A fact with no writer in one setup is a finding. Count the steps the design asks of a person, before the change and after it. A new step is a cost that the design states, never one the person finds later.

## The likely changes

Name two or three changes that are likely. Take each from the request's own "later", from the prior art, or from a number that grows. Write each as a scenario, as the skill's step 1 does: the change is the stimulus, and what it touches is the response. Say what absorbs it: new data, new code behind a boundary that exists, or a breaking change. Build none of them. Give only a breaking one the cheapest room now, such as a list in place of a single value, or state that the break is accepted later, and its cost.

## Each count

A count taken from the code or the data carries the search or the command that produced it, and the commit it ran on, so a reader can run it again. An estimate is marked as one, with its source, and `aidd-team:estimation` owns its range.

## Each removed thing

Where a design removes a thing, list each job the thing does, with each case it handles, and what holds that job after.

## Each existing part and each quality claim

Every claim that an existing part already does a job carries the command and its output, or marks the claim "read, not run". Every quality the design claims names a test with its pass-or-fail rule and, when run, its evidence.
