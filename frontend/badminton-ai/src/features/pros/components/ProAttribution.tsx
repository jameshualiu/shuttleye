type ProAttributionProps = {
  /** Which dataset the page shows. Defaults to singles. */
  source?: "singles" | "doubles";
};

export function ProAttribution({ source = "singles" }: ProAttributionProps) {
  if (source === "doubles") {
    return (
      <p className="text-sm text-muted-foreground">
        Doubles data from DShuttleNet (Kaggle, CC BY-NC-SA 4.0), labelled by professional players
        from BWF World Tour matches. Shared under the same licence; non-commercial use only.
      </p>
    );
  }
  return (
    <p className="text-sm text-muted-foreground">
      Shot data from ShuttleSet and ShuttleSet22 by the CoachAI team (Wang et al., KDD 2023; IJCAI
      2023), labelled by hand from BWF World Tour matches. Clips play from BWF's YouTube channel.
    </p>
  );
}
