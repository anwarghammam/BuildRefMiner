
# 1. Metrics – *Anwar G.*

## Complexity

A weighted formula:

```
Complexity = w₁ * (1 / CC) + w₂ * (1 / AC) + w₃ * SCS 
           + w₄ * (CR / (Comment Lines / Total Lines)) 
           + w₅ * (1 / log(LOC + 2)) 
           + w₆ * (1 - UDR) 
           + w₇ * (1 - DCR)
```

**Where:**
- `CC` = Cyclomatic Complexity  
- `AC` = (Possibly Abstract Complexity)  
- `SCS` = Source Code Simplicity  
- `CR` = Comment Ratio  
- `LOC` = Lines of Code  
- `UDR` = Unused Dependency Ratio  
- `DCR` = Dependency Conflict Ratio  

---

### SCS (Source Code Simplicity)

```
SCS = (1 - V / LOC) * 100
```

- `V` = (Possibly number of violations or unused elements)  
- `LOC` = Lines of Code

---

## Maintainability

```
Maintainability = f(Complexity, Coupling, Cohesion, Dependency Quality)
```
