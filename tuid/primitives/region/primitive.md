# Primitive: Region

A rectangular logical area.

```yaml
region:
  x:
  y:
  width:
  height:
  purpose:            # navigation · primary content · detail · status · command bar · modal · notification layer
  priority:
  overflow_behavior:  # truncate · scroll · wrap · overlay — explicit per region
```

Regions are the units of layout invariants: no viewport renders outside its
allocated region; regions don't overlap unexpectedly; priority ordering
governs what survives narrowing. Priority + overflow behavior together define
the responsive degradation of the layout.
